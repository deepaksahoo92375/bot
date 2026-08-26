"""
Local File Audio Source.
Plays audio files that already exist on disk (uploaded by admins, synced
into LOCAL_MUSIC_DIR, etc). Fully functional — no external dependency.
"""
from __future__ import annotations

import os
from pathlib import Path

from app.core.config import settings
from app.core.logging import logger
from app.services.audio_source_base import AudioSourceError, AudioSourcePlugin, ResolvedTrack

_ALLOWED_EXTENSIONS = {".mp3", ".m4a", ".flac", ".wav", ".ogg", ".opus"}


class LocalFileSource(AudioSourcePlugin):
    name = "local_file"

    def __init__(self, base_dir: str | None = None) -> None:
        self.base_dir = Path(base_dir or settings.local_music_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def can_handle(self, query: str) -> bool:
        # Treat anything that isn't a URL and resolves to a real file under base_dir as local
        if query.startswith(("http://", "https://")):
            return False
        candidate = self._safe_resolve(query)
        return candidate is not None and candidate.exists() and candidate.suffix.lower() in _ALLOWED_EXTENSIONS

    async def resolve(self, query: str) -> ResolvedTrack:
        candidate = self._safe_resolve(query)
        if candidate is None or not candidate.exists():
            raise AudioSourceError(f"Local file not found: {query}")

        title = candidate.stem
        logger.info("Resolved local file | path={}", candidate)
        return ResolvedTrack(
            title=title,
            playable_path=str(candidate),
            artist=None,
            thumbnail_url=None,
        )

    def list_library(self) -> list[str]:
        """Return relative paths of all playable files in the library."""
        results = []
        for root, _dirs, files in os.walk(self.base_dir):
            for f in files:
                if Path(f).suffix.lower() in _ALLOWED_EXTENSIONS:
                    full = Path(root) / f
                    results.append(str(full.relative_to(self.base_dir)))
        return sorted(results)

    def _safe_resolve(self, query: str) -> Path | None:
        """
        Resolve a relative path against base_dir while preventing path
        traversal outside the music library (e.g. '../../etc/passwd').
        """
        try:
            candidate = (self.base_dir / query).resolve()
            candidate.relative_to(self.base_dir)  # raises ValueError if outside base_dir
            return candidate
        except (ValueError, OSError):
            return None
