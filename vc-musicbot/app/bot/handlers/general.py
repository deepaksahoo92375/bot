"""
General/start commands.
"""
from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import Message

from app.db.repositories import user_repo

HELP_TEXT = """
**🎵 VC Music Bot — Commands**

**Playback**
`/play <url or filename>` — play or queue a track
`/skip` — skip current track
`/pause` `/resume` — pause/resume playback
`/stop` — stop and leave voice chat
`/queue` — show the queue
`/shuffle` — shuffle the queue
`/loop off|track|queue|infinite` — set loop mode
`/volume <0-200>` — set volume
`/remove <position>` — remove a track from queue

**Playlists**
`/createplaylist <name>`
`/myplaylists`
`/addtoplaylist <id> <url>`
`/playplaylist <id>`

**Discovery**
`/spotify <query>` — search Spotify metadata
`/recommend` — get AI-based recommendations from your history

**Admin**
`/settings` — view group settings
`/authuser` (reply to user) — authorize a user to control playback
`/antispam on|off`
`/logs` — recent admin actions (owner/sudo only)
`/broadcast <message>` (DM only, owner/sudo) — message all groups
`/broadcast users|all <message>` — message all users / everyone
`/dashboardlogin` (DM only) — get a one-time code for the web dashboard

Supported audio sources: **direct audio URLs** and **local files** in the music library.
"""


@Client.on_message(filters.command("start"))
async def start_cmd(client: Client, message: Message) -> None:
    if message.from_user:
        await user_repo.get_or_create(
            message.from_user.id, message.from_user.username or "", message.from_user.first_name or ""
        )
    await message.reply_text(
        "👋 **Welcome to VC Music Bot!**\n\nUse `/help` to see all commands."
    )


@Client.on_message(filters.command("help"))
async def help_cmd(client: Client, message: Message) -> None:
    await message.reply_text(HELP_TEXT)
