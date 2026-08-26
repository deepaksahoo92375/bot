"""
Spotify Metadata Service.

Uses the official Spotify Web API (Client Credentials flow) for:
  - track/album/playlist search
  - track metadata (title, artist, duration, cover art)
  - "available genre seeds" based recommendations

IMPORTANT: Spotify's Web API does not provide audio streaming for
third-party apps — this service is metadata only. To actually play a
track found here, resolve a playable source (local file / direct URL)
separately and queue that instead.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logging import logger

_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API_BASE = "https://api.spotify.com/v1"


@dataclass
class SpotifyTrackMeta:
    spotify_id: str
    title: str
    artist: str
    album: str
    duration_ms: int
    thumbnail_url: Optional[str]
    external_url: str


class SpotifyMetadataService:
    def __init__(self) -> None:
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    @property
    def configured(self) -> bool:
        return bool(settings.spotify_client_id and settings.spotify_client_secret)

    async def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 30:
            return self._token

        if not self.configured:
            raise RuntimeError("Spotify credentials not configured (SPOTIFY_CLIENT_ID/SECRET)")

        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(settings.spotify_client_id, settings.spotify_client_secret),
            )
            resp.raise_for_status()
            data = resp.json()

        self._token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 3600)
        logger.debug("Spotify access token refreshed")
        return self._token

    async def _get(self, path: str, params: dict | None = None) -> dict:
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{_API_BASE}{path}",
                headers={"Authorization": f"Bearer {token}"},
                params=params or {},
            )
            resp.raise_for_status()
            return resp.json()

    async def search_tracks(self, query: str, limit: int = 10) -> list[SpotifyTrackMeta]:
        data = await self._get("/search", {"q": query, "type": "track", "limit": limit})
        items = data.get("tracks", {}).get("items", [])
        return [self._parse_track(item) for item in items]

    async def get_track(self, spotify_track_id: str) -> SpotifyTrackMeta:
        data = await self._get(f"/tracks/{spotify_track_id}")
        return self._parse_track(data)

    async def get_playlist_tracks(self, playlist_id: str, limit: int = 50) -> list[SpotifyTrackMeta]:
        data = await self._get(f"/playlists/{playlist_id}/tracks", {"limit": limit})
        items = data.get("items", [])
        return [self._parse_track(item["track"]) for item in items if item.get("track")]

    async def get_recommendations(
        self, seed_genres: list[str], limit: int = 20
    ) -> list[SpotifyTrackMeta]:
        params = {"seed_genres": ",".join(seed_genres[:5]), "limit": limit}
        data = await self._get("/recommendations", params)
        return [self._parse_track(t) for t in data.get("tracks", [])]

    @staticmethod
    def _parse_track(item: dict) -> SpotifyTrackMeta:
        images = item.get("album", {}).get("images", [])
        thumbnail = images[0]["url"] if images else None
        return SpotifyTrackMeta(
            spotify_id=item["id"],
            title=item["name"],
            artist=", ".join(a["name"] for a in item.get("artists", [])),
            album=item.get("album", {}).get("name", ""),
            duration_ms=item.get("duration_ms", 0),
            thumbnail_url=thumbnail,
            external_url=item.get("external_urls", {}).get("spotify", ""),
        )


spotify_service = SpotifyMetadataService()
