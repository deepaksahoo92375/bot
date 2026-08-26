"""
Playlist management endpoints (dashboard CRUD view).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.db.repositories import playlist_repo

router = APIRouter()


@router.get("/owner/{owner_id}")
async def list_owner_playlists(owner_id: int) -> list[dict]:
    playlists = await playlist_repo.list_for_owner(owner_id)
    return [p.model_dump() for p in playlists]


@router.get("/{playlist_id}")
async def get_playlist(playlist_id: str) -> dict:
    playlist = await playlist_repo.get(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return playlist.model_dump()


@router.delete("/{playlist_id}")
async def delete_playlist(playlist_id: str, owner_id: int) -> dict:
    deleted = await playlist_repo.delete(playlist_id, owner_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Playlist not found or not owned by this user")
    return {"status": "deleted"}


@router.delete("/{playlist_id}/tracks/{track_id}")
async def remove_track(playlist_id: str, track_id: str) -> dict:
    await playlist_repo.remove_track(playlist_id, track_id)
    return {"status": "removed"}
