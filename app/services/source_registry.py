"""
Audio Source Registry.
Tries each registered plugin in order until one can handle the query.
"""
from __future__ import annotations

from app.core.logging import logger
from app.services.audio_source_base import AudioSourceError, AudioSourcePlugin, ResolvedTrack
from app.services.sources.direct_url_source import DirectURLSource
from app.services.sources.local_file_source import LocalFileSource
from app.services.sources.youtube_source import YouTubeSearchSource, YouTubeSource

_PLUGINS: list[AudioSourcePlugin] = [
    YouTubeSource(),        # YouTube URLs (highest priority for YT links)
    DirectURLSource(),      # Any other direct http/https audio URL
    LocalFileSource(),      # Local files in the music library
    YouTubeSearchSource(),  # Plain-text search → YouTube (catch-all)
]


async def resolve_query(query: str) -> ResolvedTrack:
    """Resolve a user-provided query (URL, search term, or local filename) into a playable track."""
    for plugin in _PLUGINS:
        try:
            if await plugin.can_handle(query):
                logger.info("Routing query to source plugin | plugin={} query={}", plugin.name, query)
                return await plugin.resolve(query)
        except AudioSourceError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning("Plugin {} raised unexpected error: {}", plugin.name, e)
            continue

    raise AudioSourceError(
        "No audio source could handle this query. "
        "Supported: YouTube URLs, YouTube search terms, direct audio URLs, local files."
    )


def register_plugin(plugin: AudioSourcePlugin) -> None:
    """Register an additional audio source plugin at runtime."""
    _PLUGINS.append(plugin)
    logger.info("Registered audio source plugin | name={}", plugin.name)
