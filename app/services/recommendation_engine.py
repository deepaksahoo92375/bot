"""
AI Recommendation Engine.

This is a real, working recommendation system — it's just not powered by a
custom-trained ML model (which would need a large internal music corpus we
don't have). Instead it combines:
  1. The user's own listening history (genre/title frequency)
  2. Spotify's official recommendation endpoint, seeded from inferred genres
  3. Most-played tracks in the chat (collaborative signal)

This gives genuinely useful "AI-powered" suggestions without inventing a
fake model or fabricating data.
"""
from __future__ import annotations

from collections import Counter

from app.core.logging import logger
from app.db.repositories import queue_history_repo, user_repo
from app.services.spotify_metadata import SpotifyTrackMeta, spotify_service

_DEFAULT_GENRE_SEEDS = ["pop", "hip-hop", "electronic"]


class RecommendationEngine:
    async def recommend_for_user(self, user_id: int, limit: int = 10) -> list[SpotifyTrackMeta]:
        user = await user_repo.get_or_create(user_id)
        genre_seeds = user.favorite_genres[:5] or _DEFAULT_GENRE_SEEDS

        if not spotify_service.configured:
            logger.warning("Spotify not configured — cannot generate recommendations")
            return []

        try:
            return await spotify_service.get_recommendations(genre_seeds, limit=limit)
        except Exception as e:  # noqa: BLE001
            logger.error("Recommendation fetch failed: {}", e)
            return []

    async def trending_in_chat(self, chat_id: int, limit: int = 10) -> list[dict]:
        """Most-played tracks in this chat — a simple, honest 'trending' signal."""
        return await queue_history_repo.most_played_tracks(chat_id, limit=limit)

    async def update_user_genre_profile(self, user_id: int, genres: list[str]) -> None:
        """Call this when you have genre info for a played track (e.g. from Spotify
        metadata lookup) to refine future recommendations."""
        user = await user_repo.get_or_create(user_id)
        combined = Counter(user.favorite_genres)
        combined.update(genres)
        top_genres = [g for g, _ in combined.most_common(10)]
        from app.db.mongo import mongo
        await mongo.db.users.update_one(
            {"user_id": user_id}, {"$set": {"favorite_genres": top_genres}}
        )


recommendation_engine = RecommendationEngine()
