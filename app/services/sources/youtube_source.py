"""
YouTube Audio Source.

Resolves YouTube URLs and search queries into a playable audio stream URL
using yt-dlp. Supports:
  - Full YouTube video URLs  (https://www.youtube.com/watch?v=...)
  - Short URLs               (https://youtu.be/...)
  - YouTube Music URLs       (https://music.youtube.com/...)
  - Plain text search        ("song name artist") — picks the top result

The resolved URL is a direct audio stream that ffmpeg / py-tgcalls can consume
without downloading the entire file first.
"""
from __future__ import annotations

import asyncio
import re
from functools import partial
from typing import Optional

from app.core.logging import logger
from app.services.audio_source_base import AudioSourceError, AudioSourcePlugin, ResolvedTrack

_YT_URL_RE = re.compile(
    r"(https?://)?(www\.)?"
    r"(youtube\.com/(watch\?.*v=|shorts/|playlist\?|embed/)|"
    r"youtu\.be/|"
    r"music\.youtube\.com/watch\?.*v=)",
    re.IGNORECASE,
)

_YDL_OPTS_BASE: dict = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "extract_flat": False,
    "noplaylist": True,
    "socket_timeout": 15,
}


def _is_youtube_url(query: str) -> bool:
    return bool(_YT_URL_RE.search(query.strip()))


def _ydl_extract(query: str, search: bool) -> dict:
    """Blocking yt-dlp extraction — run in a thread pool executor."""
    import yt_dlp  # type: ignore[import]

    opts = dict(_YDL_OPTS_BASE)
    if search:
        opts["default_search"] = "ytsearch1"

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(query, download=False)

    if info is None:
        raise AudioSourceError("yt-dlp returned no info for the query.")

    if "entries" in info:
        entries = [e for e in info["entries"] if e]
        if not entries:
            raise AudioSourceError("YouTube search returned no results.")
        info = entries[0]

    return info  # type: ignore[return-value]


def _best_stream_url(info: dict) -> str:
    """Pick the best audio-only stream URL from yt-dlp info dict."""
    url: Optional[str] = info.get("url")
    if url:
        return url

    formats: list[dict] = info.get("formats", [])
    audio_formats = [
        f for f in formats
        if f.get("vcodec") == "none" and f.get("acodec") != "none" and f.get("url")
    ]
    if audio_formats:
        audio_formats.sort(key=lambda f: f.get("abr") or 0, reverse=True)
        return audio_formats[0]["url"]

    if formats:
        return formats[-1]["url"]

    raise AudioSourceError("No playable stream URL found in yt-dlp response.")


class YouTubeSource(AudioSourcePlugin):
    name = "youtube"

    async def can_handle(self, query: str) -> bool:
        q = query.strip()
        if _is_youtube_url(q):
            return True
        if q.lower().startswith("ytsearch:"):
            return True
        return False

    async def resolve(self, query: str) -> ResolvedTrack:
        q = query.strip()
        search = not _is_youtube_url(q)

        logger.info("YouTubeSource resolving | query={} search={}", q, search)

        try:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, partial(_ydl_extract, q, search))
        except AudioSourceError:
            raise
        except Exception as e:
            raise AudioSourceError(f"yt-dlp failed: {e}") from e

        stream_url = _best_stream_url(info)

        title: str = info.get("title") or "Unknown Title"
        artist: Optional[str] = info.get("uploader") or info.get("channel") or None
        duration: Optional[int] = info.get("duration")
        thumbnail: Optional[str] = info.get("thumbnail")

        logger.info(
            "YouTubeSource resolved | title={} duration={}s",
            title, duration,
        )
        return ResolvedTrack(
            title=title,
            playable_path=stream_url,
            duration_seconds=int(duration) if duration else None,
            artist=artist,
            thumbnail_url=thumbnail,
        )


class YouTubeSearchSource(AudioSourcePlugin):
    """
    Catches plain-text search queries that aren't YouTube URLs.
    Searches YouTube and plays the top result.

    Priority in the registry should be AFTER YouTubeSource and DirectURLSource
    so explicit URLs are handled first.
    """

    name = "youtube_search"

    async def can_handle(self, query: str) -> bool:
        q = query.strip()
        if not q:
            return False
        if _is_youtube_url(q):
            return False
        if q.startswith("http://") or q.startswith("https://"):
            return False
        return len(q) >= 2

    async def resolve(self, query: str) -> ResolvedTrack:
        q = query.strip()
        logger.info("YouTubeSearchSource resolving text search | query={}", q)

        try:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, partial(_ydl_extract, q, True))
        except AudioSourceError:
            raise
        except Exception as e:
            raise AudioSourceError(f"YouTube search failed: {e}") from e

        stream_url = _best_stream_url(info)

        title: str = info.get("title") or "Unknown Title"
        artist: Optional[str] = info.get("uploader") or info.get("channel") or None
        duration: Optional[int] = info.get("duration")
        thumbnail: Optional[str] = info.get("thumbnail")

        logger.info(
            "YouTubeSearchSource resolved | title={} duration={}s",
            title, duration,
        )
        return ResolvedTrack(
            title=title,
            playable_path=stream_url,
            duration_seconds=int(duration) if duration else None,
            artist=artist,
            thumbnail_url=thumbnail,
        )
