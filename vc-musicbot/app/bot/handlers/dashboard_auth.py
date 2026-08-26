"""
Dashboard login command — DMs a one-time code to the owner/sudo user.
"""
from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import Message

from app.core.config import settings
from app.dashboard.backend.routes.auth_routes import generate_login_code


@Client.on_message(filters.command("dashboardlogin") & filters.private)
async def dashboard_login_cmd(client: Client, message: Message) -> None:
    if not message.from_user:
        return
    user_id = message.from_user.id
    if user_id != settings.owner_id and user_id not in settings.sudo_users:
        await message.reply_text("You're not authorized to access the dashboard.")
        return

    code = await generate_login_code(user_id)
    await message.reply_text(
        f"🔐 **Your dashboard login code:** `{code}`\n\n"
        f"This code expires in 5 minutes. Enter it on the dashboard login page."
    )
