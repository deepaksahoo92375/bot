"""
Application entrypoint.
Run with: python -m app.main
"""
from __future__ import annotations

import asyncio
import signal

from pyrogram import Client

from app.core.config import settings
from app.core.logging import logger
from app.db.mongo import mongo
from app.db.redis_client import redis_manager
from app.services.assistant_pool import assistant_pool
from app.services.broadcast_worker import broadcast_worker
from app.services.voice_player import voice_player
from app.services.workflow_chainer import workflow_chainer

_shutdown_event = asyncio.Event()


def _handle_signal(*_args) -> None:
    logger.info("Shutdown signal received")
    _shutdown_event.set()


async def startup() -> Client:
    logger.info("=" * 60)
    logger.info("VC Music Userbot starting up")
    logger.info("=" * 60)

    await mongo.connect()
    await redis_manager.connect()

    # Check if we're resuming after a chained workflow handoff
    handoff_state = await workflow_chainer.resume_from_handoff()
    if handoff_state:
        logger.info("Detected previous workflow handoff — will restore active chats")

    if settings.enable_multi_assistant:
        await assistant_pool.start_all()
        await voice_player.bind_assistants()
        await voice_player.restore_active_chats()

    # Bot client (commands/UI) — separate from assistant accounts
    bot_client = Client(
        name="vc_music_bot",
        api_id=settings.api_id,
        api_hash=settings.api_hash,
        bot_token=settings.bot_token,
        in_memory=True,
        plugins={"root": "app.bot.handlers"},
    )
    await bot_client.start()
    me = await bot_client.get_me()
    logger.info("Bot client started | username=@{}", me.username)

    broadcast_worker.start(bot_client)
    workflow_chainer.start_monitoring()

    return bot_client


async def shutdown(bot_client: Client) -> None:
    logger.info("Shutting down gracefully...")
    workflow_chainer.stop_monitoring()
    broadcast_worker.stop()

    try:
        await bot_client.stop()
    except Exception as e:  # noqa: BLE001
        logger.warning("Error stopping bot client: {}", e)

    if settings.enable_multi_assistant:
        await assistant_pool.stop_all()

    await redis_manager.disconnect()
    await mongo.disconnect()
    logger.info("Shutdown complete")


async def main() -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            pass  # Windows doesn't support add_signal_handler

    bot_client = await startup()

    try:
        await _shutdown_event.wait()
    finally:
        await shutdown(bot_client)


if __name__ == "__main__":
    asyncio.run(main())
