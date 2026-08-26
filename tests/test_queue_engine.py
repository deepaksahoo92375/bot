"""
Unit tests for the queue engine.
Run with: pytest tests/test_queue_engine.py
"""
from __future__ import annotations

import pytest

from app.db.models import LoopMode, SourceType, Track


def make_track(title: str) -> Track:
    return Track(title=title, source_type=SourceType.DIRECT_URL, source_ref=f"https://example.com/{title}.mp3")


@pytest.fixture
def fake_redis(monkeypatch):
    """In-memory fake for redis_manager queue methods, avoiding a real Redis dependency in unit tests."""
    store: dict[int, list[dict]] = {}
    loop_modes: dict[int, str] = {}

    class FakeRedisManager:
        async def load_queue(self, chat_id):
            return store.get(chat_id, [])

        async def save_queue(self, chat_id, queue):
            store[chat_id] = queue

        async def clear_queue(self, chat_id):
            store.pop(chat_id, None)

        async def get_json(self, key):
            if key.startswith("loop_mode:"):
                chat_id = int(key.split(":")[1])
                return loop_modes.get(chat_id)
            return None

        async def set_json(self, key, value, ex=None):
            if key.startswith("loop_mode:"):
                chat_id = int(key.split(":")[1])
                loop_modes[chat_id] = value

    from app.services import queue_engine as qe_module

    fake = FakeRedisManager()
    monkeypatch.setattr(qe_module, "redis_manager", fake)

    async def noop_log(self, chat_id, track):
        return None

    monkeypatch.setattr(qe_module.QueueEngine, "_log_history", noop_log)

    return qe_module.queue_engine


@pytest.mark.asyncio
async def test_add_and_get_queue(fake_redis):
    await fake_redis.add(1, make_track("song_a"))
    await fake_redis.add(1, make_track("song_b"))
    queue = await fake_redis.get_queue(1)
    assert len(queue) == 2
    assert queue[0].title == "song_a"


@pytest.mark.asyncio
async def test_pop_next_default_no_loop(fake_redis):
    await fake_redis.add(2, make_track("a"))
    await fake_redis.add(2, make_track("b"))
    first = await fake_redis.pop_next(2)
    assert first.title == "a"
    remaining = await fake_redis.get_queue(2)
    assert len(remaining) == 1
    assert remaining[0].title == "b"


@pytest.mark.asyncio
async def test_pop_next_track_loop_keeps_same_track(fake_redis):
    await fake_redis.add(3, make_track("a"))
    await fake_redis.add(3, make_track("b"))
    await fake_redis.set_loop_mode(3, LoopMode.TRACK)

    first = await fake_redis.pop_next(3)
    second = await fake_redis.pop_next(3)
    assert first.title == "a"
    assert second.title == "a"  # track loop never advances


@pytest.mark.asyncio
async def test_pop_next_queue_loop_recycles(fake_redis):
    await fake_redis.add(4, make_track("a"))
    await fake_redis.add(4, make_track("b"))
    await fake_redis.set_loop_mode(4, LoopMode.QUEUE)

    first = await fake_redis.pop_next(4)
    assert first.title == "a"
    queue = await fake_redis.get_queue(4)
    # "a" should be re-appended to the back
    assert [t.title for t in queue] == ["b", "a"]


@pytest.mark.asyncio
async def test_remove_at_invalid_position_returns_none(fake_redis):
    await fake_redis.add(5, make_track("a"))
    result = await fake_redis.remove_at(5, 99)
    assert result is None


@pytest.mark.asyncio
async def test_shuffle_keeps_first_track_in_place(fake_redis):
    for title in ["a", "b", "c", "d", "e"]:
        await fake_redis.add(6, make_track(title))
    shuffled = await fake_redis.shuffle(6)
    assert shuffled[0].title == "a"
    assert len(shuffled) == 5


@pytest.mark.asyncio
async def test_queue_full_raises(fake_redis, monkeypatch):
    from app.services import queue_engine as qe_module
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_queue_size", 2)
    await fake_redis.add(7, make_track("a"))
    await fake_redis.add(7, make_track("b"))
    with pytest.raises(qe_module.QueueFullError):
        await fake_redis.add(7, make_track("c"))
