"""
Assistant pool monitoring endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.db.repositories import assistant_health_repo

router = APIRouter()


@router.get("/")
async def list_assistants() -> list[dict]:
    assistants = await assistant_health_repo.all()
    return [a.model_dump() for a in assistants]


@router.get("/{label}")
async def get_assistant(label: str) -> dict | None:
    assistants = await assistant_health_repo.all()
    match = next((a for a in assistants if a.session_label == label), None)
    return match.model_dump() if match else None
