"""
Assistant Pool Manager.
Manages multiple Pyrogram "assistant" userbot clients that actually join
voice chats (the BOT_TOKEN client only handles commands/UI — Telegram bots
cannot join voice chats themselves, only user accounts can).

Responsibilities:
  - Start/stop all assistant clients
  - Pick the least-loaded healthy assistant for a new voice chat join
  - Track health (heartbeat, active call count, errors) in Mongo
  - Auto-recover: mark unhealthy assistants out of rotation, retry reconnect
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from pyrogram import Client

from app.core.config import settings
from app.core.logging import logger
from app.db.repositories import assistant_health_repo


@dataclass
class AssistantWorker:
    label: str
    client: Client
    active_calls: int = 0
    healthy: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class AssistantPoolError(Exception):
    pass


class AssistantPool:
    def __init__(self) -> None:
        self._workers: list[AssistantWorker] = []
        self._heartbeat_task: asyncio.Task | None = None

    async def start_all(self) -> None:
        sessions = settings.assistant_sessions
        if not sessions:
            raise AssistantPoolError(
                "No assistant sessions configured. Set ASSISTANT_SESSION_1 (and _2, _3...) in .env"
            )

        for idx, session_string in enumerate(sessions, start=1):
            label = f"assistant_{idx}"
            client = Client(
                name=label,
                api_id=settings.api_id,
                api_hash=settings.api_hash,
                session_string=session_string,
                in_memory=True,
            )
            try:
                await client.start()
                me = await client.get_me()
                worker = AssistantWorker(label=label, client=client, healthy=True)
                self._workers.append(worker)
                await assistant_health_repo.upsert_heartbeat(
                    label, is_online=True, active_calls=0, last_error=None
                )
                logger.info("Assistant started | label={} user={}", label, me.username or me.id)
            except Exception as e:  # noqa: BLE001
                logger.error("Failed to start assistant {}: {}", label, e)
                await assistant_health_repo.increment_error(label, str(e))

        if not self._workers:
            raise AssistantPoolError("All assistant sessions failed to start")

        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("Assistant pool started | active={}/{}", len(self._workers), len(sessions))

    async def stop_all(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        for worker in self._workers:
            try:
                await worker.client.stop()
            except Exception as e:  # noqa: BLE001
                logger.warning("Error stopping assistant {}: {}", worker.label, e)
        self._workers.clear()
        logger.info("Assistant pool stopped")

    def get_least_loaded(self) -> AssistantWorker:
        healthy = [w for w in self._workers if w.healthy]
        if not healthy:
            raise AssistantPoolError("No healthy assistants available")
        return min(healthy, key=lambda w: w.active_calls)

    def get_by_label(self, label: str) -> AssistantWorker | None:
        return next((w for w in self._workers if w.label == label), None)

    async def assign_for_chat(self) -> AssistantWorker:
        """Pick the best assistant for a new voice chat join."""
        worker = self.get_least_loaded()
        async with worker.lock:
            worker.active_calls += 1
            await assistant_health_repo.upsert_heartbeat(
                worker.label, is_online=True, active_calls=worker.active_calls
            )
        return worker

    async def release(self, label: str) -> None:
        worker = self.get_by_label(label)
        if worker is None:
            return
        async with worker.lock:
            worker.active_calls = max(0, worker.active_calls - 1)
            await assistant_health_repo.upsert_heartbeat(
                worker.label, is_online=True, active_calls=worker.active_calls
            )

    async def _heartbeat_loop(self) -> None:
        """Periodically verify each assistant connection is still alive."""
        while True:
            try:
                await asyncio.sleep(60)
                for worker in self._workers:
                    try:
                        await worker.client.get_me()
                        worker.healthy = True
                        await assistant_health_repo.upsert_heartbeat(
                            worker.label, is_online=True, active_calls=worker.active_calls
                        )
                    except Exception as e:  # noqa: BLE001
                        worker.healthy = False
                        logger.error("Assistant {} failed health check: {}", worker.label, e)
                        await assistant_health_repo.increment_error(worker.label, str(e))
                        await assistant_health_repo.upsert_heartbeat(worker.label, is_online=False)
            except asyncio.CancelledError:
                break

    @property
    def workers(self) -> list[AssistantWorker]:
        return list(self._workers)


assistant_pool = AssistantPool()
