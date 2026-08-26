"""
Inline keyboard control panel for the currently-playing track.
"""
from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.services.queue_engine import queue_engine
from app.services.voice_player import voice_player


def now_playing_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⏸ Pause", callback_data=f"vc:pause:{chat_id}"),
                InlineKeyboardButton("▶️ Resume", callback_data=f"vc:resume:{chat_id}"),
                InlineKeyboardButton("⏭ Skip", callback_data=f"vc:skip:{chat_id}"),
            ],
            [
                InlineKeyboardButton("🔀 Shuffle", callback_data=f"vc:shuffle:{chat_id}"),
                InlineKeyboardButton("📜 Queue", callback_data=f"vc:queue:{chat_id}"),
                InlineKeyboardButton("⏹ Stop", callback_data=f"vc:stop:{chat_id}"),
            ],
        ]
    )


@Client.on_callback_query(filters.regex(r"^vc:(\w+):(-?\d+)$"))
async def control_panel_callback(client: Client, cq: CallbackQuery) -> None:
    _, action, chat_id_str = cq.data.split(":")
    chat_id = int(chat_id_str)

    if action == "pause":
        await voice_player.pause(chat_id)
        await cq.answer("Paused")
    elif action == "resume":
        await voice_player.resume(chat_id)
        await cq.answer("Resumed")
    elif action == "skip":
        track = await voice_player.skip(chat_id)
        await cq.answer(f"Skipped to: {track.title}" if track else "Queue ended")
    elif action == "shuffle":
        queue = await queue_engine.shuffle(chat_id)
        await cq.answer(f"Shuffled {len(queue)} tracks")
    elif action == "queue":
        queue = await queue_engine.get_queue(chat_id)
        preview = "\n".join(f"{i+1}. {t.title}" for i, t in enumerate(queue[:10])) or "Queue is empty"
        await cq.answer(preview, show_alert=True)
    elif action == "stop":
        await voice_player.leave(chat_id)
        await cq.answer("Stopped")
        if cq.message:
            await cq.message.edit_text("⏹ Playback stopped.")
        return
    else:
        await cq.answer("Unknown action")
