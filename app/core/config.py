"""
Central configuration for the VC Music Userbot.
All environment variables are loaded and validated here ONCE.
Every other module imports `settings` from this file — never os.environ directly.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- Telegram ----------
    api_id: int = Field(..., alias="API_ID")
    api_hash: str = Field(..., alias="API_HASH")
    bot_token: str = Field(..., alias="BOT_TOKEN")

    assistant_session_1: str = Field(default="", alias="ASSISTANT_SESSION_1")
    assistant_session_2: str = Field(default="", alias="ASSISTANT_SESSION_2")
    assistant_session_3: str = Field(default="", alias="ASSISTANT_SESSION_3")

    owner_id: int = Field(..., alias="OWNER_ID")
    sudo_users_raw: str = Field(default="", alias="SUDO_USERS")

    # ---------- Database ----------
    mongo_uri: str = Field(..., alias="MONGO_URI")
    mongo_db_name: str = Field(default="vc_musicbot", alias="MONGO_DB_NAME")
    redis_url: str = Field(..., alias="REDIS_URL")

    # ---------- Spotify (metadata only) ----------
    spotify_client_id: str = Field(default="", alias="SPOTIFY_CLIENT_ID")
    spotify_client_secret: str = Field(default="", alias="SPOTIFY_CLIENT_SECRET")

    # ---------- Audio sources ----------
    local_music_dir: str = Field(default="./music_library", alias="LOCAL_MUSIC_DIR")
    max_stream_size_mb: int = Field(default=500, alias="MAX_STREAM_SIZE_MB")

    # ---------- GitHub Actions chaining ----------
    github_token: str = Field(default="", alias="GITHUB_TOKEN")
    github_repository: str = Field(default="", alias="GITHUB_REPOSITORY")
    chain_trigger_before_min: int = Field(default=15, alias="CHAIN_TRIGGER_BEFORE_MIN")
    watchdog_interval_min: int = Field(default=10, alias="WATCHDOG_INTERVAL_MIN")

    # ---------- Dashboard ----------
    dashboard_secret_key: str = Field(..., alias="DASHBOARD_SECRET_KEY")
    dashboard_port: int = Field(default=8000, alias="DASHBOARD_PORT")
    cors_origins_raw: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")

    # ---------- Logging ----------
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_to_file: bool = Field(default=True, alias="LOG_TO_FILE")

    # ---------- Feature flags ----------
    enable_ai_recommendations: bool = Field(default=True, alias="ENABLE_AI_RECOMMENDATIONS")
    enable_dashboard: bool = Field(default=True, alias="ENABLE_DASHBOARD")
    enable_multi_assistant: bool = Field(default=True, alias="ENABLE_MULTI_ASSISTANT")
    max_queue_size: int = Field(default=200, alias="MAX_QUEUE_SIZE")

    # ---------- Derived / computed ----------
    @property
    def sudo_users(self) -> List[int]:
        if not self.sudo_users_raw:
            return []
        return [int(uid.strip()) for uid in self.sudo_users_raw.split(",") if uid.strip()]

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()]

    @property
    def assistant_sessions(self) -> List[str]:
        sessions = [
            self.assistant_session_1,
            self.assistant_session_2,
            self.assistant_session_3,
        ]
        return [s for s in sessions if s]

    @field_validator("max_stream_size_mb", "max_queue_size")
    @classmethod
    def must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("must be a positive integer")
        return v


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — loaded once per process."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
