"""
Generate a Pyrogram session string for an assistant account.

This logs you into Telegram interactively (phone number + OTP code, exactly
like logging into the Telegram app itself) and prints a session string to
paste into your .env as ASSISTANT_SESSION_N. Run this once per assistant
account, locally — never run it inside CI.

Usage:
    python scripts/generate_session.py
"""
import asyncio

from pyrogram import Client


async def main() -> None:
    api_id = int(input("API ID: ").strip())
    api_hash = input("API Hash: ").strip()

    async with Client("session_gen", api_id=api_id, api_hash=api_hash, in_memory=True) as app:
        session_string = await app.export_session_string()
        print("\n" + "=" * 60)
        print("SESSION STRING (copy this into your .env file):")
        print("=" * 60)
        print(session_string)
        print("=" * 60)
        print("\nKeep this secret — it grants full access to the account.")


if __name__ == "__main__":
    asyncio.run(main())
