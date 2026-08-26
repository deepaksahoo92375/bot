"""
Spotify search commands — metadata lookup only (no audio playback from Spotify).
Use results to find a track, then queue a direct URL/local file of it via /play.
"""
from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import Message

from app.services.spotify_metadata import spotify_service


@Client.on_message(filters.command("spotify"))
async def spotify_search_cmd(client: Client, message: Message) -> None:
    if not spotify_service.configured:
        await message.reply_text(
            "Spotify integration isn't configured. Set SPOTIFY_CLIENT_ID and "
            "SPOTIFY_CLIENT_SECRET to enable metadata search."
        )
        return

    if len(message.command) < 2:
        await message.reply_text("Usage: `/spotify <search query>`")
        return

    query = message.text.split(None, 1)[1].strip()
    status = await message.reply_text(f"🔎 Searching Spotify for: `{query}`...")

    try:
        results = await spotify_service.search_tracks(query, limit=5)
    except Exception as e:  # noqa: BLE001
        await status.edit_text(f"❌ Spotify search failed: {e}")
        return

    if not results:
        await status.edit_text("No results found.")
        return

    lines = []
    for i, t in enumerate(results, 1):
        duration = f"{t.duration_ms // 60000}:{(t.duration_ms // 1000) % 60:02d}"
        lines.append(f"{i}. **{t.title}** — {t.artist} ({duration})\n   {t.external_url}")

    note = (
        "\n\n_Note: this is metadata only. To play one of these, find a direct "
        "audio URL or local file of the track and use `/play <url>`._"
    )
    await status.edit_text("**Spotify results:**\n\n" + "\n\n".join(lines) + note, disable_web_page_preview=True)
