"""
Repository pattern: one repository class per collection.
Keeps MongoDB query logic out of services/handlers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.db.mongo import mongo
from app.db.models import (
    AdminLogEntry,
    AssistantHealth,
    GroupSettings,
    Playlist,
    QueueHistoryEntry,
    Track,
    User,
)


class UserRepository:
    @property
    def col(self):
        return mongo.db.users

    async def get_or_create(self, user_id: int, username: str = "", first_name: str = "") -> User:
        doc = await self.col.find_one({"user_id": user_id})
        if doc:
            return User(**doc)
        user = User(user_id=user_id, username=username, first_name=first_name)
        await self.col.insert_one(user.model_dump())
        return user

    async def update_last_active(self, user_id: int) -> None:
        await self.col.update_one(
            {"user_id": user_id},
            {"$set": {"last_active": datetime.now(timezone.utc)}},
        )

    async def add_listening_history(self, user_id: int, track_id: str, cap: int = 200) -> None:
        await self.col.update_one(
            {"user_id": user_id},
            {"$push": {"listening_history": {"$each": [track_id], "$slice": -cap}}},
        )

    async def ban(self, user_id: int, banned: bool = True) -> None:
        await self.col.update_one({"user_id": user_id}, {"$set": {"is_banned": banned}})


class GroupRepository:
    @property
    def col(self):
        return mongo.db.groups

    async def get_or_create(self, chat_id: int, title: str = "") -> GroupSettings:
        doc = await self.col.find_one({"chat_id": chat_id})
        if doc:
            return GroupSettings(**doc)
        group = GroupSettings(chat_id=chat_id, title=title)
        await self.col.insert_one(group.model_dump())
        return group

    async def update_settings(self, chat_id: int, **fields) -> None:
        await self.col.update_one({"chat_id": chat_id}, {"$set": fields})

    async def set_assistant(self, chat_id: int, assistant_label: Optional[str]) -> None:
        await self.col.update_one({"chat_id": chat_id}, {"$set": {"assistant_label": assistant_label}})

    async def all_active_groups(self) -> list[GroupSettings]:
        cursor = self.col.find({"assistant_label": {"$ne": None}})
        return [GroupSettings(**doc) async for doc in cursor]


class PlaylistRepository:
    @property
    def col(self):
        return mongo.db.playlists

    async def create(self, playlist: Playlist) -> Playlist:
        await self.col.insert_one(playlist.model_dump())
        return playlist

    async def get(self, playlist_id: str) -> Optional[Playlist]:
        doc = await self.col.find_one({"playlist_id": playlist_id})
        return Playlist(**doc) if doc else None

    async def list_for_owner(self, owner_id: int) -> list[Playlist]:
        cursor = self.col.find({"owner_id": owner_id})
        return [Playlist(**doc) async for doc in cursor]

    async def add_track(self, playlist_id: str, track: Track) -> None:
        await self.col.update_one(
            {"playlist_id": playlist_id},
            {
                "$push": {"tracks": track.model_dump()},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
        )

    async def remove_track(self, playlist_id: str, track_id: str) -> None:
        await self.col.update_one(
            {"playlist_id": playlist_id},
            {"$pull": {"tracks": {"track_id": track_id}}},
        )

    async def delete(self, playlist_id: str, owner_id: int) -> bool:
        result = await self.col.delete_one({"playlist_id": playlist_id, "owner_id": owner_id})
        return result.deleted_count > 0


class QueueHistoryRepository:
    @property
    def col(self):
        return mongo.db.queue_history

    async def log(self, entry: QueueHistoryEntry) -> None:
        await self.col.insert_one(entry.model_dump())

    async def recent_for_chat(self, chat_id: int, limit: int = 50) -> list[QueueHistoryEntry]:
        cursor = self.col.find({"chat_id": chat_id}).sort("played_at", -1).limit(limit)
        return [QueueHistoryEntry(**doc) async for doc in cursor]

    async def most_played_tracks(self, chat_id: int, limit: int = 10) -> list[dict]:
        pipeline = [
            {"$match": {"chat_id": chat_id}},
            {"$group": {"_id": "$track.title", "play_count": {"$sum": 1}}},
            {"$sort": {"play_count": -1}},
            {"$limit": limit},
        ]
        return [doc async for doc in self.col.aggregate(pipeline)]


class AdminLogRepository:
    @property
    def col(self):
        return mongo.db.admin_logs

    async def log(self, entry: AdminLogEntry) -> None:
        await self.col.insert_one(entry.model_dump())

    async def recent_for_chat(self, chat_id: int, limit: int = 100) -> list[AdminLogEntry]:
        cursor = self.col.find({"chat_id": chat_id}).sort("timestamp", -1).limit(limit)
        return [AdminLogEntry(**doc) async for doc in cursor]


class AssistantHealthRepository:
    @property
    def col(self):
        return mongo.db.assistant_health

    async def upsert_heartbeat(self, session_label: str, **fields) -> None:
        fields["last_heartbeat"] = datetime.now(timezone.utc)
        await self.col.update_one(
            {"session_label": session_label},
            {"$set": fields},
            upsert=True,
        )

    async def all(self) -> list[AssistantHealth]:
        cursor = self.col.find({})
        return [AssistantHealth(**doc) async for doc in cursor]

    async def increment_error(self, session_label: str, error_msg: str) -> None:
        await self.col.update_one(
            {"session_label": session_label},
            {"$inc": {"error_count": 1}, "$set": {"last_error": error_msg}},
            upsert=True,
        )


# Singletons — import these directly
user_repo = UserRepository()
group_repo = GroupRepository()
playlist_repo = PlaylistRepository()
queue_history_repo = QueueHistoryRepository()
admin_log_repo = AdminLogRepository()
assistant_health_repo = AssistantHealthRepository()
