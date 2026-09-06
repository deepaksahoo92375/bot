"""
YouTube Audio Source.

Resolves YouTube URLs and search queries into a playable audio stream URL
using yt-dlp. Supports:
  - Full YouTube video URLs
  - Short YouTube URLs
  - YouTube Music URLs
  - Plain text search queries

The resolved URL is a direct audio stream that ffmpeg / py-tgcalls
can consume without downloading the entire file first.

YouTube authentication:
  - If youtube_cookies.txt exists in the project root, yt-dlp will
    automatically use it for YouTube extraction/search.
"""

from __future__ import annotations

import asyncio
import re
from functools import partial
from pathlib import Path
from typing import Optional

from app.core.logging import logger
from app.services.audio_source_base import (
    AudioSourceError,
    AudioSourcePlugin,
    ResolvedTrack,
)


# ---------------------------------------------------------------------------
# YouTube URL detection
# ---------------------------------------------------------------------------

_YT_URL_RE = re.compile(
    r"(https?://)?(www\.)?"
    r"(youtube\.com/(watch\?.*v=|shorts/|playlist\?|embed/)|"
    r"youtu\.be/|"
    r"music\.youtube\.com/watch\?.*v=)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# YouTube cookies
# ---------------------------------------------------------------------------

# GitHub Actions will create this file from the YOUTUBE_COOKIES_B64 secret.
# The file is intentionally kept outside the repository.
_YOUTUBE_COOKIES_FILE = Path("youtube_cookies.txt")


# ---------------------------------------------------------------------------
# yt-dlp configuration
# ---------------------------------------------------------------------------

_YDL_OPTS_BASE: dict = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "extract_flat": False,
    "noplaylist": True,
    "socket_timeout": 15,
}


# Automatically enable cookies when the temporary cookie file exists.
if _YOUTUBE_COOKIES_FILE.exists():
    _YDL_OPTS_BASE["cookiefile"] = str(_YOUTUBE_COOKIES_FILE)
    logger.info(
        "YouTube cookies enabled | file={}",
        _YOUTUBE_COOKIES_FILE,
    )
else:
    logger.warning(
        "YouTube cookies file not found | continuing without cookies"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_youtube_url(query: str) -> bool:
    """Return True when the query looks like a YouTube URL."""
    return bool(_YT_URL_RE.search(query.strip()))


def _ydl_extract(query: str, search: bool) -> dict:
    """
    Blocking yt-dlp extraction.

    This function is executed inside a thread pool so that yt-dlp does not
    block the asyncio event loop.
    """
    import yt_dlp  # type: ignore[import]

    opts = dict(_YDL_OPTS_BASE)

    if search:
        opts["default_search"] = "ytsearch1"

    # Make sure cookies are picked up even if the module was imported before
    # the cookie file was created.
    if _YOUTUBE_COOKIES_FILE.exists():
        opts["cookiefile"] = str(_YOUTUBE_COOKIES_FILE)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(query, download=False)
    except Exception as e:
        error_text = str(e)

        # Give the bot a cleaner error message for the common YouTube
        # anti-bot/login challenge.
        if (
            "Sign in to confirm you’re not a bot" in error_text
            or "Sign in to confirm you're not a bot" in error_text
            or "Use cookies-from-browser" in error_text
            or "Use cookies" in error_text
        ):
            raise AudioSourceError(
                "YouTube blocked this request. "
                "Please update the YouTube cookies file."
            ) from e

        raise AudioSourceError(
            f"yt-dlp extraction failed: {e}"
        ) from e

    if info is None:
        raise AudioSourceError(
            "yt-dlp returned no information for the query."
        )

    # Search results return an entries list.
    if "entries" in info:
        entries = [entry for entry in info["entries"] if entry]

        if not entries:
            raise AudioSourceError(
                "YouTube search returned no results."
            )

        info = entries[0]

    return info  # type: ignore[return-value]


def _best_stream_url(info: dict) -> str:
    """
    Pick the best audio-only stream URL from the yt-dlp info dictionary.
    """
    url: Optional[str] = info.get("url")

    if url:
        return url

    formats: list[dict] = info.get("formats", [])

    audio_formats = [
        fmt
        for fmt in formats
        if (
            fmt.get("vcodec") == "none"
            and fmt.get("acodec") != "none"
            and fmt.get("url")
        )
    ]

    if audio_formats:
        audio_formats.sort(
            key=lambda fmt: fmt.get("abr") or 0,
            reverse=True,
        )

        return audio_formats[0]["url"]

    if formats:
        for fmt in reversed(formats):
            if fmt.get("url"):
                return fmt["url"]

    raise AudioSourceError(
        "No playable stream URL found in yt-dlp response."
    )


def _build_track(info: dict) -> ResolvedTrack:
    """
    Convert a yt-dlp info dictionary into a ResolvedTrack.
    """
    stream_url = _best_stream_url(info)

    title: str = info.get("title") or "Unknown Title"

    artist: Optional[str] = (
        info.get("uploader")
        or info.get("channel")
        or None
    )

    duration: Optional[int] = info.get("duration")

    thumbnail: Optional[str] = info.get("thumbnail")

    logger.info(
        "YouTubeSource resolved | title={} duration={}s",
        title,
        duration,
    )

    return ResolvedTrack(
        title=title,
        playable_path=stream_url,
        duration_seconds=int(duration) if duration else None,
        artist=artist,
        thumbnail_url=thumbnail,
    )


# ---------------------------------------------------------------------------
# YouTube URL source
# ---------------------------------------------------------------------------

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

        logger.info(
            "YouTubeSource resolving | query={} search={}",
            q,
            search,
        )

        try:
            loop = asyncio.get_event_loop()

            info = await loop.run_in_executor(
                None,
                partial(
                    _ydl_extract,
                    q,
                    search,
                ),
            )

        except AudioSourceError:
            raise

        except Exception as e:
            raise AudioSourceError(
                f"yt-dlp failed: {e}"
            ) from e

        return _build_track(info)


# ---------------------------------------------------------------------------
# YouTube search source
# ---------------------------------------------------------------------------

class YouTubeSearchSource(AudioSourcePlugin):
    """
    Catches plain-text search queries that are not YouTube URLs.

    Example:
        /play Shape of You Ed Sheeran

    The first YouTube search result is selected.

    Priority in the registry should be AFTER YouTubeSource and
    DirectURLSource so explicit URLs are handled first.
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

        logger.info(
            "YouTubeSearchSource resolving text search | query={}",
            q,
        )

        try:
            loop = asyncio.get_event_loop()

            info = await loop.run_in_executor(
                None,
                partial(
                    _ydl_extract,
                    q,
                    True,
                ),
            )

        except AudioSourceError:
            raise

        except Exception as e:
            raise AudioSourceError(
                f"YouTube search failed: {e}"
            ) from e

        return _build_track(info)
