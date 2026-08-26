"""
Queue Engine.
Pure logic for managing a per-chat playback queue. State is persisted to
Redis (fast, ephemeral, survives workflow handoff) and mirrored to Mongo
queue_history for analytics once a track finishes playing.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone

from app.core.config import settings
from app.core.logging import logger
from app.db.models import LoopMode, QueueHistoryEntry, Track
from app.db.redis_client import redis_manager
from app.db.repositories import queue_history_repo


class QueueFullError(Exception):
    pass


class QueueEngine:
    async def get_queue(self, chat_id: int) -> list[Track]:
        raw = await redis_manager.load_queue(chat_id)
        return [Track(**t) for t in raw]

    async def _save(self, chat_id: int, queue: list[Track]) -> None:
        await redis_manager.save_queue(chat_id, [t.model_dump(mode="json") for t in queue])

    async def add(self, chat_id: int, track: Track) -> int:
        """Add a track to the end of the queue. Returns the track's position (1-indexed)."""
        queue = await self.get_queue(chat_id)
        if len(queue) >= settings.max_queue_size:
            raise QueueFullError(f"Queue is full (max {settings.max_queue_size} tracks)")
        queue.append(track)
        await self._save(chat_id, queue)
        logger.info("Track queued | chat_id={} title={} position={}", chat_id, track.title, len(queue))
        return len(queue)

    async def pop_next(self, chat_id: int) -> Track | None:
        """Remove and return the next track to play, respecting loop mode."""
        queue = await self.get_queue(chat_id)
        if not queue:
            return None

        current = queue[0]
        loop_mode = await self._get_loop_mode(chat_id)

        if loop_mode == LoopMode.TRACK:
            # keep current track at front, don't pop
            return current

        # pop it off
        queue = queue[1:]

        if loop_mode in (LoopMode.QUEUE, LoopMode.INFINITE):
            queue.append(current)  # re-append to the back

        await self._save(chat_id, queue)
        await self._log_history(chat_id, current)
        return current

    async def peek_next(self, chat_id: int) -> Track | None:
        queue = await self.get_queue(chat_id)
        return queue[0] if queue else None

    async def remove_at(self, chat_id: int, position: int) -> Track | None:
        """1-indexed removal."""
        queue = await self.get_queue(chat_id)
        idx = position - 1
        if idx < 0 or idx >= len(queue):
            return None
        removed = queue.pop(idx)
        await self._save(chat_id, queue)
        return removed

    async def clear(self, chat_id: int) -> None:
        await redis_manager.clear_queue(chat_id)
        logger.info("Queue cleared | chat_id={}", chat_id)

    async def shuffle(self, chat_id: int) -> list[Track]:
        queue = await self.get_queue(chat_id)
        if len(queue) <= 1:
            return queue
        head, rest = queue[0], queue[1:]
        random.shuffle(rest)
        new_queue = [head, *rest]
        await self._save(chat_id, new_queue)
        logger.info("Queue shuffled | chat_id={} size={}", chat_id, len(new_queue))
        return new_queue

    async def move(self, chat_id: int, from_pos: int, to_pos: int) -> bool:
        queue = await self.get_queue(chat_id)
        fi, ti = from_pos - 1, to_pos - 1
        if not (0 <= fi < len(queue)) or not (0 <= ti < len(queue)):
            return False
        track = queue.pop(fi)
        queue.insert(ti, track)
        await self._save(chat_id, queue)
        return True

    async def set_loop_mode(self, chat_id: int, mode: LoopMode) -> None:
        await redis_manager.set_json(f"loop_mode:{chat_id}", mode.value)

    async def _get_loop_mode(self, chat_id: int) -> LoopMode:
        raw = await redis_manager.get_json(f"loop_mode:{chat_id}")
        return LoopMode(raw) if raw else LoopMode.OFF

    async def _log_history(self, chat_id: int, track: Track) -> None:
        entry = QueueHistoryEntry(chat_id=chat_id, track=track, played_at=datetime.now(timezone.utc))
        await queue_history_repo.log(entry)


queue_engine = QueueEngine()
