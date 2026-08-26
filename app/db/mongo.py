"""
MongoDB connection manager using Motor (async driver).
Single shared client across the app — call `mongo.connect()` once at startup.
"""
from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings
from app.core.logging import logger


class MongoManager:
    def __init__(self) -> None:
        self._client: AsyncIOMotorClient | None = None
        self._db: AsyncIOMotorDatabase | None = None

    async def connect(self) -> None:
        if self._client is not None:
            return
        logger.info("Connecting to MongoDB Atlas...")
        self._client = AsyncIOMotorClient(
            settings.mongo_uri,
            serverSelectionTimeoutMS=8000,
            maxPoolSize=50,
            minPoolSize=5,
        )
        self._db = self._client[settings.mongo_db_name]
        # Fail fast if the cluster is unreachable
        await self._client.admin.command("ping")
        await self._ensure_indexes()
        logger.info("MongoDB connected | db={}", settings.mongo_db_name)

    async def disconnect(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            logger.info("MongoDB connection closed")

    @property
    def db(self) -> AsyncIOMotorDatabase:
        if self._db is None:
            raise RuntimeError("MongoDB not connected — call mongo.connect() first")
        return self._db

    async def _ensure_indexes(self) -> None:
        """Create indexes idempotently. Safe to call on every startup."""
        db = self.db
        await db.users.create_index("user_id", unique=True)
        await db.groups.create_index("chat_id", unique=True)
        await db.playlists.create_index([("owner_id", 1), ("name", 1)])
        await db.playlists.create_index("playlist_id", unique=True)
        await db.queue_history.create_index([("chat_id", 1), ("played_at", -1)])
        await db.admin_logs.create_index([("chat_id", 1), ("timestamp", -1)])
        await db.assistant_health.create_index("session_label", unique=True)
        await db.bot_state.create_index("key", unique=True)
        logger.debug("MongoDB indexes ensured")


mongo = MongoManager()
