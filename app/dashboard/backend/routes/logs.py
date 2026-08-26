"""
Live log tailing endpoint.
Reads from the capped Redis list that app/core/logging.py pushes into.
"""
from __future__ import annotations

import json

from fastapi import APIRouter

from app.db.redis_client import redis_manager

router = APIRouter()


@router.get("/recent")
async def recent_logs(limit: int = 200, level: str | None = None) -> list[dict]:
    raw_entries = await redis_manager.client.lrange("live_logs", 0, limit - 1)
    entries = [json.loads(e) for e in raw_entries]
    if level:
        entries = [e for e in entries if e["level"] == level.upper()]
    return entries
