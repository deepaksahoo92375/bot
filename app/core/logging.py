"""
Structured logging configuration.
Import `logger` from this module everywhere instead of using `print` or stdlib logging.
"""
import sys
from pathlib import Path

from loguru import logger

from app.core.config import settings

_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


def _add_redis_sink() -> None:
    """Push recent log lines into a capped Redis list so the dashboard can
    tail live logs without reading log files off disk (which doesn't work
    across the dashboard's separate process/container)."""
    import json
    import time

    def redis_sink(message) -> None:
        record = message.record
        try:
            import redis as _redis_sync

            # Lightweight sync client just for this sink — avoids needing
            # an async context inside loguru's sink callback.
            client = _redis_sync.Redis.from_url(settings.redis_url, decode_responses=True)
            entry = {
                "time": record["time"].isoformat(),
                "level": record["level"].name,
                "message": record["message"],
                "module": record["name"],
            }
            client.lpush("live_logs", json.dumps(entry))
            client.ltrim("live_logs", 0, 499)  # keep last 500 lines
        except Exception:
            pass  # never let logging itself crash the app

    logger.add(redis_sink, level="INFO", enqueue=True)


def setup_logging() -> None:
    logger.remove()  # remove default handler

    logger.add(
        sys.stderr,
        format=_LOG_FORMAT,
        level=settings.log_level,
        colorize=True,
        backtrace=True,
        diagnose=False,  # never leak variable values in prod logs
    )

    if settings.log_to_file:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        logger.add(
            log_dir / "bot_{time:YYYY-MM-DD}.log",
            format=_LOG_FORMAT,
            level=settings.log_level,
            rotation="00:00",       # new file every day
            retention="14 days",
            compression="zip",
            enqueue=True,           # async-safe writes
            backtrace=True,
            diagnose=False,
        )
        logger.add(
            log_dir / "errors_{time:YYYY-MM-DD}.log",
            format=_LOG_FORMAT,
            level="ERROR",
            rotation="00:00",
            retention="30 days",
            compression="zip",
            enqueue=True,
        )

    logger.info("Logging initialized | level={}", settings.log_level)
    _add_redis_sink()


setup_logging()
__all__ = ["logger"]
