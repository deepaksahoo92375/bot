"""
Admin & moderation commands.
"""
from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import Message

from app.core.config import settings
from app.db.models import AdminLogEntry
from app.db.repositories import admin_log_repo, group_repo


def _is_authorized(user_id: int, group_auth_users: list[int]) -> bool:
    return user_id == settings.owner_id or user_id in settings.sudo_users or user_id in group_auth_users


@Client.on_message(filters.command("settings") & filters.group)
async def settings_cmd(client: Client, message: Message) -> None:
    group = await group_repo.get_or_create(message.chat.id, message.chat.title or "")
    text = (
        f"**Group Settings**\n"
        f"Loop mode: `{group.loop_mode.value}`\n"
        f"Volume: `{group.volume}`\n"
        f"Bass boost: `{group.bass_boost}`\n"
        f"Anti-spam: `{group.anti_spam_enabled}`\n"
        f"Anti-flood: `{group.anti_flood_enabled}`\n"
        f"Link protection: `{group.link_protection}`\n"
    )
    await message.reply_text(text)


@Client.on_message(filters.command("authuser") & filters.group)
async def authuser_cmd(client: Client, message: Message) -> None:
    if not message.from_user:
        return
    chat_member = await client.get_chat_member(message.chat.id, message.from_user.id)
    if not chat_member.privileges and message.from_user.id != settings.owner_id:
        await message.reply_text("Only group admins can authorize users.")
        return

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply_text("Reply to a user's message to authorize them.")
        return

    target_id = message.reply_to_message.from_user.id
    group = await group_repo.get_or_create(message.chat.id, message.chat.title or "")
    if target_id not in group.auth_users:
        updated = group.auth_users + [target_id]
        await group_repo.update_settings(message.chat.id, auth_users=updated)

    await admin_log_repo.log(
        AdminLogEntry(
            chat_id=message.chat.id,
            actor_id=message.from_user.id,
            action="authuser",
            details={"target_id": target_id},
        )
    )
    await message.reply_text(f"✅ User authorized to control playback.")


@Client.on_message(filters.command("antispam") & filters.group)
async def antispam_cmd(client: Client, message: Message) -> None:
    if not message.from_user:
        return
    chat_member = await client.get_chat_member(message.chat.id, message.from_user.id)
    if not chat_member.privileges:
        await message.reply_text("Only group admins can change this setting.")
        return

    if len(message.command) < 2 or message.command[1].lower() not in ("on", "off"):
        await message.reply_text("Usage: `/antispam on|off`")
        return

    enabled = message.command[1].lower() == "on"
    await group_repo.update_settings(message.chat.id, anti_spam_enabled=enabled)
    await message.reply_text(f"🛡 Anti-spam {'enabled' if enabled else 'disabled'}.")


@Client.on_message(filters.command("logs") & filters.group)
async def logs_cmd(client: Client, message: Message) -> None:
    if not message.from_user or message.from_user.id not in (settings.owner_id, *settings.sudo_users):
        await message.reply_text("Only the owner/sudo users can view logs.")
        return
    entries = await admin_log_repo.recent_for_chat(message.chat.id, limit=15)
    if not entries:
        await message.reply_text("No admin log entries yet.")
        return
    lines = [f"`{e.timestamp:%Y-%m-%d %H:%M}` — user {e.actor_id} — {e.action}" for e in entries]
    await message.reply_text("**Recent admin actions:**\n" + "\n".join(lines))
