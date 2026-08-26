"""
Recommendation command.
"""
from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import Message

from app.services.recommendation_engine import recommendation_engine


@Client.on_message(filters.command("recommend"))
async def recommend_cmd(client: Client, message: Message) -> None:
    if not message.from_user:
        return
    status = await message.reply_text("🎧 Building recommendations...")
    results = await recommendation_engine.recommend_for_user(message.from_user.id)

    if not results:
        await status.edit_text(
            "No recommendations available right now — make sure Spotify credentials "
            "are configured, or play a few tracks first so we learn your taste."
        )
        return

    lines = [f"{i+1}. **{t.title}** — {t.artist}\n   {t.external_url}" for i, t in enumerate(results)]
    await status.edit_text(
        "**🎧 Recommended for you:**\n\n" + "\n\n".join(lines),
        disable_web_page_preview=True,
    )


@Client.on_message(filters.command("trending") & filters.group)
async def trending_cmd(client: Client, message: Message) -> None:
    from app.services.recommendation_engine import recommendation_engine as engine

    results = await engine.trending_in_chat(message.chat.id)
    if not results:
        await message.reply_text("No play history yet for this chat.")
        return

    lines = [f"{i+1}. {r['_id']} — played {r['play_count']}x" for i, r in enumerate(results)]
    await message.reply_text("**🔥 Trending in this chat:**\n" + "\n".join(lines))
