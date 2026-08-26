"""
Broadcast command — owner/sudo only.
Usage:
    /broadcast <message>            -> sends to all groups
    /broadcast users <message>      -> sends to all DM'd users
    /broadcast all <message>        -> sends to both
Reply to a message with /broadcast to forward that message's content instead.
"""
from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import Message

from app.core.config import settings
from app.db.models import AdminLogEntry
from app.db.repositories import admin_log_repo
from app.services.broadcast_service import broadcast_service

_TARGET_KEYWORDS = {"users", "all", "groups"}


def _is_owner_or_sudo(user_id: int) -> bool:
    return user_id == settings.owner_id or user_id in settings.sudo_users


@Client.on_message(filters.command("broadcast") & filters.private)
async def broadcast_cmd(client: Client, message: Message) -> None:
    if not message.from_user or not _is_owner_or_sudo(message.from_user.id):
        await message.reply_text("Only the owner/sudo users can broadcast.")
        return

    args = message.text.split(None, 2)
    target = "groups"
    text = None

    if len(args) >= 2 and args[1].lower() in _TARGET_KEYWORDS:
        target = args[1].lower()
        text = args[2] if len(args) > 2 else None
    elif len(args) >= 2:
        text = message.text.split(None, 1)[1]

    if message.reply_to_message and message.reply_to_message.text:
        text = message.reply_to_message.text

    if not text:
        await message.reply_text(
            "Usage:\n"
            "`/broadcast <message>` — to all groups\n"
            "`/broadcast users <message>` — to all users\n"
            "`/broadcast all <message>` — to everyone\n"
            "or reply to a message with `/broadcast`."
        )
        return

    status = await message.reply_text(f"📢 Broadcasting to **{target}**...")

    if target == "groups":
        result = await broadcast_service.broadcast_to_groups(client, text)
    elif target == "users":
        result = await broadcast_service.broadcast_to_users(client, text)
    else:
        result = await broadcast_service.broadcast_to_all(client, text)

    await admin_log_repo.log(
        AdminLogEntry(
            chat_id=message.chat.id,
            actor_id=message.from_user.id,
            action="broadcast",
            details={"target": target, "sent": result.sent, "failed": result.failed},
        )
    )

    await status.edit_text(
        f"✅ **Broadcast complete**\n"
        f"Target: `{target}`\n"
        f"Total: `{result.total_targets}`\n"
        f"Sent: `{result.sent}`\n"
        f"Failed: `{result.failed}`"
    )
