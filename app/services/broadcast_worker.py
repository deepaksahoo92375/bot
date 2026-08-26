"""
Broadcast Job Worker.
Runs inside the bot process (which holds the live Pyrogram client) and polls
Redis for broadcast jobs queued by the dashboard. Decouples the dashboard
(stateless FastAPI process) from needing its own Telegram client.
"""
from __future__ import annotations

import asyncio

from pyrogram import Client

from app.core.logging import logger
from app.db.redis_client import redis_manager
from app.services.broadcast_service import broadcast_service

_POLL_INTERVAL_SECONDS = 2


class BroadcastWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    def start(self, bot_client: Client) -> None:
        self._task = asyncio.create_task(self._loop(bot_client))
        logger.info("Broadcast job worker started")

    def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _loop(self, bot_client: Client) -> None:
        while True:
            try:
                job_id = await redis_manager.client.lpop("broadcast_queue")
                if not job_id:
                    await asyncio.sleep(_POLL_INTERVAL_SECONDS)
                    continue

                job = await redis_manager.get_json(f"broadcast_job:{job_id}")
                if not job:
                    continue

                logger.info("Processing broadcast job | job_id={} target={}", job_id, job["target"])
                job["status"] = "running"
                await redis_manager.set_json(f"broadcast_job:{job_id}", job, ex=3600)

                if job["target"] == "groups":
                    result = await broadcast_service.broadcast_to_groups(bot_client, job["text"])
                elif job["target"] == "users":
                    result = await broadcast_service.broadcast_to_users(bot_client, job["text"])
                else:
                    result = await broadcast_service.broadcast_to_all(bot_client, job["text"])

                job["status"] = "completed"
                job["sent"] = result.sent
                job["failed"] = result.failed
                job["total"] = result.total_targets
                await redis_manager.set_json(f"broadcast_job:{job_id}", job, ex=3600)

            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001
                logger.error("Broadcast worker error: {}", e)
                await asyncio.sleep(_POLL_INTERVAL_SECONDS)


broadcast_worker = BroadcastWorker()
