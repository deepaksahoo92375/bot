"""
Lightweight anti-spam / anti-flood moderation.
Tracks message rate per user per chat in Redis; mutes/warns on threshold breach.
This runs as a low-priority message handler (group=10) so it doesn't block
command processing, but still observes every message.
"""
from __future__ import annotations

import time

from pyrogram import Client, filters
from pyrogram.types import Message

from app.core.logging import logger
from app.db.redis_client import redis_manager
from app.db.repositories import group_repo

_FLOOD_WINDOW_SECONDS = 10
_FLOOD_MAX_MESSAGES = 8


@Client.on_message(filters.group, group=10)
async def moderation_filter(client: Client, message: Message) -> None:
    if not message.from_user:
        return

    group = await group_repo.get_or_create(message.chat.id, message.chat.title or "")
    if not group.anti_flood_enabled:
        return

    key = f"flood:{message.chat.id}:{message.from_user.id}"
    now = time.time()

    client_redis = redis_manager.client
    await client_redis.zadd(key, {str(now): now})
    await client_redis.zremrangebyscore(key, 0, now - _FLOOD_WINDOW_SECONDS)
    await client_redis.expire(key, _FLOOD_WINDOW_SECONDS * 2)
    count = await client_redis.zcard(key)

    if count > _FLOOD_MAX_MESSAGES:
        try:
            await client.restrict_chat_member(
                message.chat.id,
                message.from_user.id,
                permissions=None,  # mute — Pyrogram default restricts all perms when None-equivalent applied
            )
            await message.reply_text(
                f"🚫 {message.from_user.mention} has been muted for flooding."
            )
            logger.info(
                "User muted for flooding | chat_id={} user_id={}",
                message.chat.id,
                message.from_user.id,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not mute flooding user (likely missing admin rights): {}", e)
