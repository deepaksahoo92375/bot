"""
Playlist management commands — create, list, add, remove, play.
"""
from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import Message

from app.db.models import Playlist, SourceType, Track
from app.db.repositories import playlist_repo
from app.services.audio_source_base import AudioSourceError
from app.services.queue_engine import queue_engine
from app.services.source_registry import resolve_query
from app.services.voice_player import voice_player


@Client.on_message(filters.command("createplaylist"))
async def create_playlist_cmd(client: Client, message: Message) -> None:
    if len(message.command) < 2 or not message.from_user:
        await message.reply_text("Usage: `/createplaylist <name>`")
        return
    name = message.text.split(None, 1)[1].strip()
    playlist = Playlist(name=name, owner_id=message.from_user.id)
    await playlist_repo.create(playlist)
    await message.reply_text(f"✅ Playlist **{name}** created.\nID: `{playlist.playlist_id}`")


@Client.on_message(filters.command("myplaylists"))
async def my_playlists_cmd(client: Client, message: Message) -> None:
    if not message.from_user:
        return
    playlists = await playlist_repo.list_for_owner(message.from_user.id)
    if not playlists:
        await message.reply_text("You have no playlists yet. Create one with `/createplaylist <name>`.")
        return
    lines = [f"• **{p.name}** ({len(p.tracks)} tracks) — `{p.playlist_id}`" for p in playlists]
    await message.reply_text("**Your playlists:**\n" + "\n".join(lines))


@Client.on_message(filters.command("addtoplaylist"))
async def add_to_playlist_cmd(client: Client, message: Message) -> None:
    if len(message.command) < 3:
        await message.reply_text("Usage: `/addtoplaylist <playlist_id> <url or filename>`")
        return
    _, playlist_id, *query_parts = message.text.split(None, 2)
    query = query_parts[0] if query_parts else ""

    playlist = await playlist_repo.get(playlist_id)
    if not playlist:
        await message.reply_text("Playlist not found.")
        return

    try:
        resolved = await resolve_query(query)
    except AudioSourceError as e:
        await message.reply_text(f"❌ {e}")
        return

    track = Track(
        title=resolved.title,
        artist=resolved.artist,
        source_type=SourceType.DIRECT_URL if resolved.playable_path.startswith("http") else SourceType.LOCAL_FILE,
        source_ref=resolved.playable_path,
        requested_by=message.from_user.id if message.from_user else None,
    )
    await playlist_repo.add_track(playlist_id, track)
    await message.reply_text(f"➕ Added **{track.title}** to playlist.")


@Client.on_message(filters.command("playplaylist") & filters.group)
async def play_playlist_cmd(client: Client, message: Message) -> None:
    if len(message.command) < 2:
        await message.reply_text("Usage: `/playplaylist <playlist_id>`")
        return
    playlist_id = message.command[1]
    playlist = await playlist_repo.get(playlist_id)
    if not playlist or not playlist.tracks:
        await message.reply_text("Playlist not found or empty.")
        return

    chat_id = message.chat.id
    first, rest = playlist.tracks[0], playlist.tracks[1:]
    await voice_player.join_and_play(chat_id, first)
    for track in rest:
        await queue_engine.add(chat_id, track)

    await message.reply_text(f"▶️ Playing playlist **{playlist.name}** ({len(playlist.tracks)} tracks).")
