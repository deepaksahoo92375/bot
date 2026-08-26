"""
Unit tests for audio source plugins (local file + direct URL).
"""
from __future__ import annotations

import pytest

from app.services.audio_source_base import AudioSourceError
from app.services.sources.local_file_source import LocalFileSource


@pytest.fixture
def tmp_music_dir(tmp_path):
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "test_song.mp3").write_bytes(b"fake mp3 data")
    sub = music_dir / "album"
    sub.mkdir()
    (sub / "track2.flac").write_bytes(b"fake flac data")
    return music_dir


@pytest.mark.asyncio
async def test_local_file_can_handle_existing_file(tmp_music_dir):
    source = LocalFileSource(base_dir=str(tmp_music_dir))
    assert await source.can_handle("test_song.mp3") is True


@pytest.mark.asyncio
async def test_local_file_rejects_missing_file(tmp_music_dir):
    source = LocalFileSource(base_dir=str(tmp_music_dir))
    assert await source.can_handle("nonexistent.mp3") is False


@pytest.mark.asyncio
async def test_local_file_rejects_urls(tmp_music_dir):
    source = LocalFileSource(base_dir=str(tmp_music_dir))
    assert await source.can_handle("https://example.com/song.mp3") is False


@pytest.mark.asyncio
async def test_local_file_path_traversal_blocked(tmp_music_dir):
    source = LocalFileSource(base_dir=str(tmp_music_dir))
    # Attempt to escape the music library directory
    assert await source.can_handle("../../../etc/passwd") is False


@pytest.mark.asyncio
async def test_local_file_resolve_returns_track(tmp_music_dir):
    source = LocalFileSource(base_dir=str(tmp_music_dir))
    resolved = await source.resolve("test_song.mp3")
    assert resolved.title == "test_song"
    assert resolved.playable_path.endswith("test_song.mp3")


@pytest.mark.asyncio
async def test_local_file_resolve_missing_raises(tmp_music_dir):
    source = LocalFileSource(base_dir=str(tmp_music_dir))
    with pytest.raises(AudioSourceError):
        await source.resolve("missing.mp3")


def test_list_library_finds_nested_files(tmp_music_dir):
    source = LocalFileSource(base_dir=str(tmp_music_dir))
    files = source.list_library()
    assert "test_song.mp3" in files
    assert any("track2.flac" in f for f in files)
