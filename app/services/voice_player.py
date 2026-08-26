"""
Voice Chat Player.
Wraps Py-TgCalls to join/leave/stream into Telegram voice chats, and wires
up the queue engine so finishing a track automatically advances to the next.
"""
from __future__ import annotations

import asyncio

from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream
from pytgcalls.types.stream import StreamEnded

from app.core.logging import logger
from app.db.models import Track
from app.db.redis_client import redis_manager
from app.db.repositories import group_repo
from app.services.assistant_pool import assistant_pool
from app.services.queue_engine import queue_engine


class VoiceChatPlayer:
    def __init__(self) -> None:
        # One PyTgCalls binding per assistant client, keyed by assistant label
        self._calls: dict[str, PyTgCalls] = {}
        self._chat_assistant: dict[int, str] = {}  # chat_id -> assistant label

    async def bind_assistants(self) -> None:
        for worker in assistant_pool.workers:
            call_binding = PyTgCalls(worker.client)
            await call_binding.start()
            call_binding.on_stream_end()(self._make_stream_end_handler(worker.label))
            self._calls[worker.label] = call_binding
        logger.info("PyTgCalls bound for {} assistants", len(self._calls))

    def _make_stream_end_handler(self, assistant_label: str):
        async def handler(_client: PyTgCalls, update: StreamEnded) -> None:
            chat_id = update.chat_id
            logger.info("Stream ended | chat_id={} assistant={}", chat_id, assistant_label)
            await self._advance_queue(chat_id, assistant_label)
        return handler

    async def join_and_play(self, chat_id: int, track: Track) -> str:
        """Join the voice chat (if not already joined) and start streaming `track`.
        Returns the assistant label handling this chat."""
        if chat_id in self._chat_assistant:
            label = self._chat_assistant[chat_id]
            await self._play_track(label, chat_id, track)
            return label

        worker = await assistant_pool.assign_for_chat()
        self._chat_assistant[chat_id] = worker.label
        await group_repo.set_assistant(chat_id, worker.label)
        await redis_manager.register_active_chat(chat_id, {"assistant": worker.label})

        await self._play_track(worker.label, chat_id, track)
        logger.info("Joined voice chat | chat_id={} assistant={}", chat_id, worker.label)
        return worker.label

    async def _play_track(self, assistant_label: str, chat_id: int, track: Track) -> None:
        call = self._calls.get(assistant_label)
        if call is None:
            raise RuntimeError(f"No PyTgCalls binding for assistant {assistant_label}")

        stream = MediaStream(track.source_ref)
        try:
            await call.play(chat_id, stream)
        except Exception:
            # Not yet in the call — join fresh
            await call.play(chat_id, stream)

    async def skip(self, chat_id: int) -> Track | None:
        label = self._chat_assistant.get(chat_id)
        if label is None:
            return None
        return await self._advance_queue(chat_id, label, force=True)

    async def _advance_queue(self, chat_id: int, assistant_label: str, force: bool = False) -> Track | None:
        next_track = await queue_engine.pop_next(chat_id)
        if next_track is None:
            await self.leave(chat_id)
            return None
        await self._play_track(assistant_label, chat_id, next_track)
        return next_track

    async def pause(self, chat_id: int) -> bool:
        label = self._chat_assistant.get(chat_id)
        if not label:
            return False
        await self._calls[label].pause(chat_id)
        return True

    async def resume(self, chat_id: int) -> bool:
        label = self._chat_assistant.get(chat_id)
        if not label:
            return False
        await self._calls[label].resume(chat_id)
        return True

    async def set_volume(self, chat_id: int, volume: int) -> bool:
        label = self._chat_assistant.get(chat_id)
        if not label:
            return False
        await self._calls[label].change_volume_call(chat_id, max(0, min(200, volume)))
        return True

    async def leave(self, chat_id: int) -> None:
        label = self._chat_assistant.pop(chat_id, None)
        if label is None:
            return
        try:
            await self._calls[label].leave_call(chat_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("Error leaving call | chat_id={} error={}", chat_id, e)
        await assistant_pool.release(label)
        await group_repo.set_assistant(chat_id, None)
        await redis_manager.unregister_active_chat(chat_id)
        await queue_engine.clear(chat_id)
        logger.info("Left voice chat | chat_id={} assistant={}", chat_id, label)

    async def restore_active_chats(self) -> None:
        """Called on startup (incl. after a chained workflow restart) to resume
        any voice chats that were active before the previous job was killed."""
        active = await redis_manager.get_active_chats()
        for chat_id, data in active.items():
            label = data.get("assistant")
            worker = assistant_pool.get_by_label(label) if label else None
            if worker is None:
                worker = await assistant_pool.assign_for_chat()
                label = worker.label
            self._chat_assistant[chat_id] = label
            next_track = await queue_engine.peek_next(chat_id)
            if next_track:
                try:
                    await self._play_track(label, chat_id, next_track)
                    logger.info("Resumed voice chat after restart | chat_id={}", chat_id)
                except Exception as e:  # noqa: BLE001
                    logger.error("Failed to resume chat_id={}: {}", chat_id, e)


voice_player = VoiceChatPlayer()
