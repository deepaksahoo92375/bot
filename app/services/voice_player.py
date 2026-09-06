"""
Voice Chat Player.

Wraps Py-TgCalls to join/leave/stream into Telegram voice chats,
and wires up the queue engine so finishing a track automatically
advances to the next.
"""

from __future__ import annotations

import asyncio

# ---------------------------------------------------------------------------
# Pyrogram / PyTgCalls compatibility
#
# Some PyTgCalls releases expect GroupcallForbidden to exist in
# pyrogram.errors. Older Pyrogram 2.x releases may not expose that name.
# Define a compatible fallback before importing PyTgCalls.
# ---------------------------------------------------------------------------

try:
    import pyrogram.errors as pyrogram_errors

    if not hasattr(pyrogram_errors, "GroupcallForbidden"):
        base_forbidden = getattr(
            pyrogram_errors,
            "Forbidden",
            Exception,
        )

        class GroupcallForbidden(base_forbidden):
            """Compatibility fallback for PyTgCalls."""

        pyrogram_errors.GroupcallForbidden = GroupcallForbidden

except Exception:
    # If Pyrogram itself cannot be imported, PyTgCalls will raise the
    # appropriate import/configuration error below.
    pass


from pytgcalls import PyTgCalls
from pytgcalls import filters as fl
from pytgcalls.types import MediaStream
from pytgcalls.types.stream import StreamEnded

from app.core.logging import logger
from app.db.models import Track
from app.db.redis_client import redis_manager
from app.db.repositories import group_repo
from app.services.assistant_pool import assistant_pool
from app.services.queue_engine import queue_engine


class VoiceChatPlayer:
    """Manage Telegram voice-chat playback through PyTgCalls."""

    def __init__(self) -> None:
        # One PyTgCalls binding per assistant.
        self._calls: dict[str, PyTgCalls] = {}

        # chat_id -> assistant label.
        self._chat_assistant: dict[int, str] = {}

        # Prevent two simultaneous playback operations for the same chat.
        self._chat_locks: dict[int, asyncio.Lock] = {}

    def _get_chat_lock(self, chat_id: int) -> asyncio.Lock:
        lock = self._chat_locks.get(chat_id)

        if lock is None:
            lock = asyncio.Lock()
            self._chat_locks[chat_id] = lock

        return lock

    async def bind_assistants(self) -> None:
        """
        Create one PyTgCalls instance for every started assistant.

        The assistant_pool must already be started before this method runs.
        """

        self._calls.clear()

        for worker in assistant_pool.workers:
            try:
                logger.info(
                    "Binding PyTgCalls | assistant={}",
                    worker.label,
                )

                call_binding = PyTgCalls(worker.client)

                await call_binding.start()

                # ----------------------------------------------------------------
                # PyTgCalls 2.2.x event API
                #
                # PyTgCalls 2.2.11 does NOT provide:
                #
                #     call_binding.on_stream_end()
                #
                # Stream-ended events are registered through:
                #
                #     call_binding.on_update(fl.stream_end())
                # ----------------------------------------------------------------

                @call_binding.on_update(fl.stream_end())
                async def stream_end_handler(
                    _client: PyTgCalls,
                    update: StreamEnded,
                    assistant_label: str = worker.label,
                ) -> None:
                    handler = self._make_stream_end_handler(
                        assistant_label
                    )

                    await handler(
                        _client,
                        update,
                    )

                self._calls[worker.label] = call_binding

                logger.info(
                    "PyTgCalls bound | assistant={}",
                    worker.label,
                )

            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Failed to bind PyTgCalls | assistant={} error={}",
                    worker.label,
                    exc,
                )

                # Continue trying other assistants rather than silently
                # hiding which assistant failed.
                continue

        if not self._calls:
            raise RuntimeError(
                "No PyTgCalls bindings could be created. "
                "Check Pyrogram/PyTgCalls compatibility."
            )

        logger.info(
            "PyTgCalls bound for {} assistants",
            len(self._calls),
        )

    def _make_stream_end_handler(self, assistant_label: str):
        """
        Create the handler that runs when a stream finishes.

        The handler advances the queue automatically. If there is no
        next track, _advance_queue() will leave the voice chat.
        """

        async def handler(
            _client: PyTgCalls,
            update: StreamEnded,
        ) -> None:
            chat_id = update.chat_id

            logger.info(
                "Stream ended | chat_id={} assistant={}",
                chat_id,
                assistant_label,
            )

            try:
                await self._advance_queue(
                    chat_id,
                    assistant_label,
                )

            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Failed to advance queue | chat_id={} error={}",
                    chat_id,
                    exc,
                )

        return handler

    async def join_and_play(
        self,
        chat_id: int,
        track: Track,
    ) -> str:
        """
        Join the voice chat if necessary and start streaming the track.

        Returns the assistant label handling this chat.
        """

        lock = self._get_chat_lock(chat_id)

        async with lock:
            if chat_id in self._chat_assistant:
                label = self._chat_assistant[chat_id]

                await self._play_track(
                    label,
                    chat_id,
                    track,
                )

                return label

            worker = await assistant_pool.assign_for_chat()

            label = worker.label

            self._chat_assistant[chat_id] = label

            await group_repo.set_assistant(
                chat_id,
                label,
            )

            await redis_manager.register_active_chat(
                chat_id,
                {
                    "assistant": label,
                },
            )

            try:
                await self._play_track(
                    label,
                    chat_id,
                    track,
                )

            except Exception:
                # Roll back assignment if joining/playing failed.
                self._chat_assistant.pop(
                    chat_id,
                    None,
                )

                try:
                    await group_repo.set_assistant(
                        chat_id,
                        None,
                    )
                except Exception:
                    pass

                try:
                    await redis_manager.unregister_active_chat(
                        chat_id,
                    )
                except Exception:
                    pass

                try:
                    await assistant_pool.release(
                        label,
                    )
                except Exception:
                    pass

                raise

            logger.info(
                "Joined voice chat | chat_id={} assistant={}",
                chat_id,
                label,
            )

            return label

    async def _play_track(
        self,
        assistant_label: str,
        chat_id: int,
        track: Track,
    ) -> None:
        call = self._calls.get(
            assistant_label,
        )

        if call is None:
            raise RuntimeError(
                f"No PyTgCalls binding for assistant {assistant_label}"
            )

        source = track.source_ref

        if not source:
            raise ValueError(
                f"Track has no source_ref | chat_id={chat_id}"
            )

        logger.info(
            "Playing track | chat_id={} assistant={} source={}",
            chat_id,
            assistant_label,
            source,
        )

        stream = MediaStream(source)

        await call.play(
            chat_id,
            stream,
        )

    async def skip(
        self,
        chat_id: int,
    ) -> Track | None:
        label = self._chat_assistant.get(
            chat_id,
        )

        if label is None:
            return None

        lock = self._get_chat_lock(
            chat_id,
        )

        async with lock:
            return await self._advance_queue(
                chat_id,
                label,
                force=True,
            )

    async def _advance_queue(
        self,
        chat_id: int,
        assistant_label: str,
        force: bool = False,
    ) -> Track | None:
        next_track = await queue_engine.pop_next(
            chat_id,
        )

        if next_track is None:
            await self.leave(
                chat_id,
            )

            return None

        try:
            await self._play_track(
                assistant_label,
                chat_id,
                next_track,
            )

        except Exception:
            logger.exception(
                "Failed to play next track | chat_id={} assistant={}",
                chat_id,
                assistant_label,
            )

            raise

        return next_track

    async def pause(
        self,
        chat_id: int,
    ) -> bool:
        label = self._chat_assistant.get(
            chat_id,
        )

        if not label:
            return False

        call = self._calls.get(
            label,
        )

        if call is None:
            return False

        await call.pause(
            chat_id,
        )

        return True

    async def resume(
        self,
        chat_id: int,
    ) -> bool:
        label = self._chat_assistant.get(
            chat_id,
        )

        if not label:
            return False

        call = self._calls.get(
            label,
        )

        if call is None:
            return False

        await call.resume(
            chat_id,
        )

        return True

    async def set_volume(
        self,
        chat_id: int,
        volume: int,
    ) -> bool:
        label = self._chat_assistant.get(
            chat_id,
        )

        if not label:
            return False

        call = self._calls.get(
            label,
        )

        if call is None:
            return False

        volume = max(
            0,
            min(
                200,
                volume,
            ),
        )

        await call.change_volume_call(
            chat_id,
            volume,
        )

        return True

    async def leave(
        self,
        chat_id: int,
    ) -> None:
        label = self._chat_assistant.pop(
            chat_id,
            None,
        )

        if label is None:
            return

        call = self._calls.get(
            label,
        )

        if call is not None:
            try:
                await call.leave_call(
                    chat_id,
                )

            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Error leaving call | chat_id={} error={}",
                    chat_id,
                    exc,
                )

        try:
            await assistant_pool.release(
                label,
            )

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to release assistant | assistant={} error={}",
                label,
                exc,
            )

        try:
            await group_repo.set_assistant(
                chat_id,
                None,
            )

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to clear group assistant | chat_id={} error={}",
                chat_id,
                exc,
            )

        try:
            await redis_manager.unregister_active_chat(
                chat_id,
            )

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to unregister active chat | chat_id={} error={}",
                chat_id,
                exc,
            )

        try:
            await queue_engine.clear(
                chat_id,
            )

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to clear queue | chat_id={} error={}",
                chat_id,
                exc,
            )

        self._chat_locks.pop(
            chat_id,
            None,
        )

        logger.info(
            "Left voice chat | chat_id={} assistant={}",
            chat_id,
            label,
        )

    async def restore_active_chats(self) -> None:
        """
        Called on startup, including after a chained workflow restart,
        to resume voice chats that were active before the previous job
        was killed.
        """

        active = await redis_manager.get_active_chats()

        if not active:
            logger.info(
                "No active voice chats to restore"
            )

            return

        logger.info(
            "Restoring {} active voice chats",
            len(active),
        )

        for chat_id, data in active.items():
            try:
                label = data.get(
                    "assistant"
                )

                worker = (
                    assistant_pool.get_by_label(
                        label
                    )
                    if label
                    else None
                )

                if worker is None:
                    worker = await assistant_pool.assign_for_chat()
                    label = worker.label

                self._chat_assistant[chat_id] = label

                next_track = await queue_engine.peek_next(
                    chat_id
                )

                if next_track is None:
                    logger.info(
                        "No queued track to restore | chat_id={}",
                        chat_id,
                    )

                    continue

                await self._play_track(
                    label,
                    chat_id,
                    next_track,
                )

                logger.info(
                    "Resumed voice chat after restart | chat_id={} assistant={}",
                    chat_id,
                    label,
                )

            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Failed to resume chat_id={} error={}",
                    chat_id,
                    exc,
                )


voice_player = VoiceChatPlayer()
