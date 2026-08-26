"""
Broadcast endpoint — lets the dashboard trigger a broadcast without needing
to go through the bot's DM. Requires the bot client to be reachable, so this
publishes a job to Redis that the running bot process picks up and executes
(keeps the dashboard process decoupled from holding a live Pyrogram client).
"""
from __future__ import annotations

import time
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from app.db.redis_client import redis_manager

router = APIRouter()


class BroadcastRequest(BaseModel):
    target: str  # "groups" | "users" | "all"
    text: str


class BroadcastJobResponse(BaseModel):
    job_id: str
    status: str = "queued"


@router.post("/", response_model=BroadcastJobResponse)
async def queue_broadcast(payload: BroadcastRequest) -> BroadcastJobResponse:
    job_id = uuid.uuid4().hex
    job = {
        "job_id": job_id,
        "target": payload.target,
        "text": payload.text,
        "created_at": time.time(),
        "status": "queued",
    }
    await redis_manager.set_json(f"broadcast_job:{job_id}", job, ex=3600)
    await redis_manager.client.rpush("broadcast_queue", job_id)
    return BroadcastJobResponse(job_id=job_id)


@router.get("/{job_id}")
async def get_broadcast_status(job_id: str) -> dict | None:
    return await redis_manager.get_json(f"broadcast_job:{job_id}")
