"""
Backup script — exports all MongoDB collections to timestamped JSON files.
Run manually or on a schedule (e.g. via APScheduler or a separate cron-style
GitHub Actions workflow).

Usage:
    python scripts/backup.py [--out-dir backups/]
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.logging import logger
from app.db.mongo import mongo

_COLLECTIONS = [
    "users",
    "groups",
    "playlists",
    "queue_history",
    "admin_logs",
    "assistant_health",
    "bot_state",
]


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


async def backup(out_dir: Path) -> None:
    await mongo.connect()
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    for name in _COLLECTIONS:
        docs = [doc async for doc in mongo.db[name].find({})]
        file_path = out_dir / f"{name}_{timestamp}.json"
        file_path.write_text(json.dumps(docs, default=_json_default, indent=2))
        logger.info("Backed up {} documents from '{}' -> {}", len(docs), name, file_path)

    await mongo.disconnect()
    logger.info("Backup complete: {} collections -> {}", len(_COLLECTIONS), out_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="backups", help="Directory to write backup files to")
    args = parser.parse_args()
    asyncio.run(backup(Path(args.out_dir)))
