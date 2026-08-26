"""
Playback command handlers.
"""
from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import Message

from app.core.logging import logger
from app.db.models import LoopMode, SourceType, Track
from app.db.repositories import group_repo, user_repo
from app.services.audio_source_base import AudioSourceError
from app.services.queue_engine import queue_engine
from app.services.source_registry import resolve_query
from app.services.sources.youtube_source import _is_youtube_url
from app.services.voice_player import voice_player


def _detect_source_type(query: str, playable_path: str) -> SourceType:
    if _is_youtube_url(query) or query.lower().startswith("ytsearch:"):
        return SourceType.YOUTUBE
    if not playable_path.startswith("http"):
        return SourceType.LOCAL_FILE
    return SourceType.DIRECT_URL


@Client.on_message(filters.command("play") & filters.group)
async def play_cmd(client: Client, message: Message) -> None:
    if len(message.command) < 2:
        await message.reply_text(
            "Usage: `/play <YouTube URL or search term>`\n\n"
            "**Examples:**\n"
            "• `/play https://youtube.com/watch?v=dQw4w9WgXcQ`\n"
            "• `/play never gonna give you up`\n"
            "• `/play lo-fi hip hop beats`\n\n"
            "Also supports: direct audio URLs, local files in the music library.",
        )
        return

    query = message.text.split(None, 1)[1].strip()
    chat_id = message.chat.id
    user = message.from_user

    await user_repo.get_or_create(user.id, user.username or "", user.first_name or "")
    await group_repo.get_or_create(chat_id, message.chat.title or "")

    status_msg = await message.reply_text(f"🔎 Resolving: `{query}`...")

    try:
        resolved = await resolve_query(query)
    except AudioSourceError as e:
        await status_msg.edit_text(f"❌ Couldn't play that: {e}")
        return

    track = Track(
        title=resolved.title,
        artist=resolved.artist,
        duration_seconds=resolved.duration_seconds,
        source_type=_detect_source_type(query, resolved.playable_path),
        source_ref=resolved.playable_path,
        thumbnail_url=resolved.thumbnail_url,
        requested_by=user.id,
    )

    existing_queue = await queue_engine.get_queue(chat_id)

    if not existing_queue:
        await voice_player.join_and_play(chat_id, track)
        await status_msg.edit_text(f"▶️ **Now playing:** {track.title}")
    else:
        position = await queue_engine.add(chat_id, track)
        await status_msg.edit_text(f"➕ **Queued at #{position}:** {track.title}")


@Client.on_message(filters.command("skip") & filters.group)
async def skip_cmd(client: Client, message: Message) -> None:
    next_track = await voice_player.skip(message.chat.id)
    if next_track:
        await message.reply_text(f"⏭ **Skipped. Now playing:** {next_track.title}")
    else:
        await message.reply_text("⏭ Skipped. Queue is empty — left the voice chat.")


@Client.on_message(filters.command("pause") & filters.group)
async def pause_cmd(client: Client, message: Message) -> None:
    ok = await voice_player.pause(message.chat.id)
    await message.reply_text("⏸ Paused." if ok else "Nothing is playing.")


@Client.on_message(filters.command("resume") & filters.group)
async def resume_cmd(client: Client, message: Message) -> None:
    ok = await voice_player.resume(message.chat.id)
    await message.reply_text("▶️ Resumed." if ok else "Nothing is paused.")


@Client.on_message(filters.command("stop") & filters.group)
async def stop_cmd(client: Client, message: Message) -> None:
    await voice_player.leave(message.chat.id)
    await message.reply_text("⏹ Stopped and left the voice chat.")


@Client.on_message(filters.command("queue") & filters.group)
async def queue_cmd(client: Client, message: Message) -> None:
    queue = await queue_engine.get_queue(message.chat.id)
    if not queue:
        await message.reply_text("Queue is empty.")
        return
    lines = [f"{i+1}. {t.title}" for i, t in enumerate(queue[:20])]
    extra = f"\n...and {len(queue) - 20} more" if len(queue) > 20 else ""
    await message.reply_text("**Queue:**\n" + "\n".join(lines) + extra)


@Client.on_message(filters.command("shuffle") & filters.group)
async def shuffle_cmd(client: Client, message: Message) -> None:
    queue = await queue_engine.shuffle(message.chat.id)
    await message.reply_text(f"🔀 Shuffled {len(queue)} tracks.")


@Client.on_message(filters.command("loop") & filters.group)
async def loop_cmd(client: Client, message: Message) -> None:
    if len(message.command) < 2:
        await message.reply_text("Usage: `/loop off|track|queue|infinite`")
        return
    mode_str = message.command[1].lower()
    try:
        mode = LoopMode(mode_str)
    except ValueError:
        await message.reply_text("Invalid mode. Use: off, track, queue, or infinite.")
        return
    await queue_engine.set_loop_mode(message.chat.id, mode)
    await message.reply_text(f"🔁 Loop mode set to **{mode.value}**.")


@Client.on_message(filters.command("volume") & filters.group)
async def volume_cmd(client: Client, message: Message) -> None:
    if len(message.command) < 2 or not message.command[1].isdigit():
        await message.reply_text("Usage: `/volume <0-200>`")
        return
    vol = int(message.command[1])
    ok = await voice_player.set_volume(message.chat.id, vol)
    await message.reply_text(f"🔊 Volume set to {vol}." if ok else "Nothing is playing.")


@Client.on_message(filters.command("remove") & filters.group)
async def remove_cmd(client: Client, message: Message) -> None:
    if len(message.command) < 2 or not message.command[1].isdigit():
        await message.reply_text("Usage: `/remove <queue position>`")
        return
    pos = int(message.command[1])
    track = await queue_engine.remove_at(message.chat.id, pos)
    if track:
        await message.reply_text(f"🗑 Removed: {track.title}")
    else:
        await message.reply_text("Invalid position.")
