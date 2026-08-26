"""
Direct URL Audio Source.
Streams audio from any publicly-accessible direct URL (e.g. a podcast RSS
enclosure, a self-hosted file, a CDN link to audio you have rights to play).

This does basic safety checks (content-type, size limit via HEAD request)
before handing the URL off to ffmpeg/py-tgcalls — it does not download
or cache the whole file unless you choose to.
"""
from __future__ import annotations

import re

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.services.audio_source_base import AudioSourceError, AudioSourcePlugin, ResolvedTrack

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_AUDIO_CONTENT_TYPES = (
    "audio/",
    "application/ogg",
    "video/mp4",  # some CDNs mislabel audio-only mp4 as video/mp4
    "application/octet-stream",  # generic — allowed but logged as uncertain
)


class DirectURLSource(AudioSourcePlugin):
    name = "direct_url"

    async def can_handle(self, query: str) -> bool:
        return bool(_URL_RE.match(query.strip()))

    async def resolve(self, query: str) -> ResolvedTrack:
        url = query.strip()
        if not await self.can_handle(url):
            raise AudioSourceError(f"Not a valid direct URL: {url}")

        await self._validate(url)

        title = url.rsplit("/", 1)[-1].split("?")[0] or "Direct Stream"
        logger.info("Resolved direct URL source | url={}", url)
        return ResolvedTrack(
            title=title,
            playable_path=url,  # py-tgcalls / ffmpeg can stream straight from the URL
        )

    async def _validate(self, url: str) -> None:
        """HEAD request to confirm reachability, content-type, and size limits
        before committing to streaming it into a voice chat."""
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=8.0) as client:
                resp = await client.head(url)
        except httpx.HTTPError as e:
            raise AudioSourceError(f"Could not reach URL: {e}") from e

        if resp.status_code >= 400:
            raise AudioSourceError(f"URL returned HTTP {resp.status_code}")

        content_type = resp.headers.get("content-type", "").lower()
        if content_type and not any(content_type.startswith(t) for t in _AUDIO_CONTENT_TYPES):
            raise AudioSourceError(f"URL does not appear to be audio (content-type={content_type})")

        content_length = resp.headers.get("content-length")
        if content_length:
            size_mb = int(content_length) / (1024 * 1024)
            if size_mb > settings.max_stream_size_mb:
                raise AudioSourceError(
                    f"File too large: {size_mb:.1f}MB exceeds limit of {settings.max_stream_size_mb}MB"
                )
