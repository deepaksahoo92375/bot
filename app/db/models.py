"""
Data models for every MongoDB collection.
These are plain Pydantic models used for validation/serialization —
Motor stores them as dicts via `.model_dump()`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class LoopMode(str, Enum):
    OFF = "off"
    TRACK = "track"
    QUEUE = "queue"
    INFINITE = "infinite"


class SourceType(str, Enum):
    DIRECT_URL = "direct_url"
    LOCAL_FILE = "local_file"
    YOUTUBE = "youtube"                    # resolved via yt-dlp (URL or search)
    SPOTIFY_METADATA = "spotify_metadata"  # metadata lookup; playback still needs a URL/file


class AdminRole(str, Enum):
    OWNER = "owner"
    SUDO = "sudo"
    GROUP_ADMIN = "group_admin"
    DJ = "dj"
    MEMBER = "member"


# ---------------------------------------------------------------------------
# Core documents
# ---------------------------------------------------------------------------

class User(BaseModel):
    user_id: int
    username: Optional[str] = None
    first_name: str = ""
    is_banned: bool = False
    listening_history: list[str] = Field(default_factory=list)  # track ids, capped externally
    favorite_genres: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    last_active: datetime = Field(default_factory=_now)


class GroupSettings(BaseModel):
    chat_id: int
    title: str = ""
    loop_mode: LoopMode = LoopMode.OFF
    volume: int = 100
    bass_boost: bool = False
    equalizer_preset: str = "flat"
    auth_users: list[int] = Field(default_factory=list)   # users allowed to control playback
    anti_spam_enabled: bool = True
    anti_flood_enabled: bool = True
    link_protection: bool = False
    assistant_label: Optional[str] = None  # which assistant currently in VC
    created_at: datetime = Field(default_factory=_now)


class Track(BaseModel):
    """A single track reference — not the audio itself."""
    track_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    title: str
    artist: Optional[str] = None
    duration_seconds: Optional[int] = None
    source_type: SourceType
    source_ref: str  # URL or local file path
    thumbnail_url: Optional[str] = None
    requested_by: Optional[int] = None
    added_at: datetime = Field(default_factory=_now)


class Playlist(BaseModel):
    playlist_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str
    owner_id: int
    is_collaborative: bool = False
    collaborators: list[int] = Field(default_factory=list)
    tracks: list[Track] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class QueueHistoryEntry(BaseModel):
    chat_id: int
    track: Track
    played_at: datetime = Field(default_factory=_now)
    skipped: bool = False


class AdminLogEntry(BaseModel):
    chat_id: int
    actor_id: int
    action: str
    details: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_now)


class AssistantHealth(BaseModel):
    session_label: str
    is_online: bool = False
    active_calls: int = 0
    last_heartbeat: datetime = Field(default_factory=_now)
    error_count: int = 0
    last_error: Optional[str] = None


class BotState(BaseModel):
    """Generic key-value store for cross-restart persistent state (non-queue)."""
    key: str
    value: dict
    updated_at: datetime = Field(default_factory=_now)
