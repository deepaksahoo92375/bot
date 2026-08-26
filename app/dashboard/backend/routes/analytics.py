"""
Analytics endpoints.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from app.db.mongo import mongo
from app.db.redis_client import redis_manager

router = APIRouter()


@router.get("/overview")
async def overview() -> dict:
    active_chats = await redis_manager.get_active_chats()
    total_groups = await mongo.db.groups.count_documents({})
    total_users = await mongo.db.users.count_documents({})

    since = datetime.now(timezone.utc) - timedelta(days=1)
    songs_played_24h = await mongo.db.queue_history.count_documents({"played_at": {"$gte": since}})

    return {
        "active_voice_chats": len(active_chats),
        "total_groups": total_groups,
        "total_users": total_users,
        "songs_played_24h": songs_played_24h,
    }


@router.get("/active-chats")
async def active_chats() -> dict:
    return await redis_manager.get_active_chats()


@router.get("/top-tracks")
async def top_tracks(limit: int = 20) -> list[dict]:
    pipeline = [
        {"$group": {"_id": "$track.title", "play_count": {"$sum": 1}}},
        {"$sort": {"play_count": -1}},
        {"$limit": limit},
    ]
    return [doc async for doc in mongo.db.queue_history.aggregate(pipeline)]


@router.get("/daily-active-users")
async def daily_active_users(days: int = 7) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    pipeline = [
        {"$match": {"last_active": {"$gte": since}}},
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$last_active"}},
                "active_users": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    return [doc async for doc in mongo.db.users.aggregate(pipeline)]


@router.get("/errors")
async def recent_errors(limit: int = 50) -> list[dict]:
    cursor = mongo.db.assistant_health.find({"last_error": {"$ne": None}}).limit(limit)
    return [doc async for doc in cursor]
