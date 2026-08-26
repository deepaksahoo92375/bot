"""
Connected groups endpoints — which groups the bot is in, when they were
added, whether they're currently playing, and per-group play history.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.db.mongo import mongo
from app.db.redis_client import redis_manager
from app.db.repositories import queue_history_repo

router = APIRouter()


@router.get("/")
async def list_groups() -> list[dict]:
    active_chats = await redis_manager.get_active_chats()
    cursor = mongo.db.groups.find({})
    groups = []
    async for doc in cursor:
        chat_id = doc["chat_id"]
        groups.append(
            {
                "chat_id": chat_id,
                "title": doc.get("title", ""),
                "created_at": doc.get("created_at"),
                "loop_mode": doc.get("loop_mode", "off"),
                "currently_playing": chat_id in active_chats,
                "assistant": active_chats.get(chat_id, {}).get("assistant"),
            }
        )
    # currently-playing groups first
    groups.sort(key=lambda g: g["currently_playing"], reverse=True)
    return groups


@router.get("/{chat_id}/history")
async def group_play_history(chat_id: int, limit: int = 50) -> list[dict]:
    entries = await queue_history_repo.recent_for_chat(chat_id, limit=limit)
    if not entries:
        # Distinguish "no history" from "group doesn't exist"
        exists = await mongo.db.groups.find_one({"chat_id": chat_id})
        if not exists:
            raise HTTPException(status_code=404, detail="Group not found")
    return [
        {
            "title": e.track.title,
            "artist": e.track.artist,
            "played_at": e.played_at,
            "requested_by": e.track.requested_by,
            "skipped": e.skipped,
        }
        for e in entries
    ]
