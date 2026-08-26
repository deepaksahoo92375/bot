"""
Redis connection manager.
Used for: active queue state, session/runtime caching, fast lookups,
and as the handoff mechanism between chained GitHub Actions workflow runs.
"""
from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import logger


class RedisManager:
    def __init__(self) -> None:
        self._client: aioredis.Redis | None = None

    async def connect(self) -> None:
        if self._client is not None:
            return
        logger.info("Connecting to Redis...")
        self._client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=50,
        )
        await self._client.ping()
        logger.info("Redis connected")

    async def disconnect(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Redis connection closed")

    @property
    def client(self) -> aioredis.Redis:
        if self._client is None:
            raise RuntimeError("Redis not connected — call redis_manager.connect() first")
        return self._client

    # ---------- Convenience helpers ----------

    async def set_json(self, key: str, value: Any, ex: int | None = None) -> None:
        await self.client.set(key, json.dumps(value), ex=ex)

    async def get_json(self, key: str) -> Any | None:
        raw = await self.client.get(key)
        return json.loads(raw) if raw is not None else None

    async def delete(self, *keys: str) -> None:
        if keys:
            await self.client.delete(*keys)

    # ---------- Queue state (per chat) ----------

    def _queue_key(self, chat_id: int) -> str:
        return f"queue:{chat_id}"

    async def save_queue(self, chat_id: int, queue: list[dict]) -> None:
        await self.set_json(self._queue_key(chat_id), queue)

    async def load_queue(self, chat_id: int) -> list[dict]:
        return await self.get_json(self._queue_key(chat_id)) or []

    async def clear_queue(self, chat_id: int) -> None:
        await self.delete(self._queue_key(chat_id))

    # ---------- Active voice chats registry ----------

    async def register_active_chat(self, chat_id: int, data: dict) -> None:
        await self.client.hset("active_chats", str(chat_id), json.dumps(data))

    async def unregister_active_chat(self, chat_id: int) -> None:
        await self.client.hdel("active_chats", str(chat_id))

    async def get_active_chats(self) -> dict[int, dict]:
        raw = await self.client.hgetall("active_chats")
        return {int(k): json.loads(v) for k, v in raw.items()}

    # ---------- Workflow handoff state (GitHub Actions chaining) ----------

    async def save_handoff_state(self, payload: dict) -> None:
        """Snapshot of everything the NEXT workflow run needs to resume seamlessly."""
        await self.set_json("workflow:handoff_state", payload, ex=3600)

    async def load_handoff_state(self) -> dict | None:
        return await self.get_json("workflow:handoff_state")


redis_manager = RedisManager()
