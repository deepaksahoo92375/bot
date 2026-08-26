"""
Audio Source Plugin Interface.

Every audio provider (direct URL, local file, or anything you add yourself)
implements this interface. The queue engine and voice chat player only ever
talk to this interface — they don't know or care where the audio came from.

To add a new source (e.g. your own YouTube/SoundCloud resolver):
    1. Subclass AudioSourcePlugin
    2. Implement `resolve()` to return a ResolvedTrack with a playable
       local path or direct stream URL that ffmpeg/py-tgcalls can consume
    3. Register it in app/services/source_registry.py

This repo ships with DirectURLSource and LocalFileSource only.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ResolvedTrack:
    title: str
    playable_path: str          # local file path OR a direct, already-accessible stream URL
    duration_seconds: Optional[int] = None
    artist: Optional[str] = None
    thumbnail_url: Optional[str] = None


class AudioSourceError(Exception):
    """Raised when a source plugin cannot resolve a query into playable audio."""


class AudioSourcePlugin(ABC):
    """Base interface every audio source must implement."""

    name: str = "base"

    @abstractmethod
    async def can_handle(self, query: str) -> bool:
        """Return True if this plugin recognizes/can process the given query."""
        raise NotImplementedError

    @abstractmethod
    async def resolve(self, query: str) -> ResolvedTrack:
        """
        Turn a user query (URL or search string) into a ResolvedTrack
        with a path/URL that's actually playable right now.
        Must raise AudioSourceError if resolution fails.
        """
        raise NotImplementedError
