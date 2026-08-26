"""
Broadcast Service.
Sends a message to all groups the bot is in, all known users, or both.
Rate-limited to avoid hitting Telegram's flood limits, and logs results
(success/fail counts, which chats failed) so the owner can see what happened.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from pyrogram import Client
from pyrogram.errors import FloodWait, RPCError

from app.core.logging import logger
from app.db.mongo import mongo

_SEND_DELAY_SECONDS = 0.05  # ~20 messages/sec ceiling, well under Telegram's limits


@dataclass
class BroadcastResult:
    total_targets: int = 0
    sent: int = 0
    failed: int = 0
    failed_ids: list[int] = field(default_factory=list)


class BroadcastService:
    async def broadcast_to_groups(self, client: Client, text: str) -> BroadcastResult:
        chat_ids = [doc["chat_id"] async for doc in mongo.db.groups.find({}, {"chat_id": 1})]
        return await self._send_to_targets(client, chat_ids, text)

    async def broadcast_to_users(self, client: Client, text: str) -> BroadcastResult:
        user_ids = [doc["user_id"] async for doc in mongo.db.users.find({"is_banned": False}, {"user_id": 1})]
        return await self._send_to_targets(client, user_ids, text)

    async def broadcast_to_all(self, client: Client, text: str) -> BroadcastResult:
        groups = await self.broadcast_to_groups(client, text)
        users = await self.broadcast_to_users(client, text)
        return BroadcastResult(
            total_targets=groups.total_targets + users.total_targets,
            sent=groups.sent + users.sent,
            failed=groups.failed + users.failed,
            failed_ids=groups.failed_ids + users.failed_ids,
        )

    async def _send_to_targets(self, client: Client, target_ids: list[int], text: str) -> BroadcastResult:
        result = BroadcastResult(total_targets=len(target_ids))

        for target_id in target_ids:
            try:
                await client.send_message(target_id, text)
                result.sent += 1
            except FloodWait as e:
                logger.warning("Broadcast hit FloodWait, sleeping {}s", e.value)
                await asyncio.sleep(e.value)
                try:
                    await client.send_message(target_id, text)
                    result.sent += 1
                except RPCError as e2:
                    result.failed += 1
                    result.failed_ids.append(target_id)
                    logger.warning("Broadcast failed for {} after retry: {}", target_id, e2)
            except RPCError as e:
                result.failed += 1
                result.failed_ids.append(target_id)
                logger.debug("Broadcast failed for {}: {}", target_id, e)

            await asyncio.sleep(_SEND_DELAY_SECONDS)

        logger.info(
            "Broadcast complete | total={} sent={} failed={}",
            result.total_targets, result.sent, result.failed,
        )
        return result


broadcast_service = BroadcastService()
