"""
Login flow: owner/sudo requests a one-time code via the bot's DM (sent by
a bot command, not implemented in HTTP — see app/bot/handlers/dashboard_auth.py),
then exchanges that code here for a JWT.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.dashboard.backend.auth import create_access_token
from app.db.redis_client import redis_manager

router = APIRouter()

_CODE_TTL_SECONDS = 300


class CodeVerifyRequest(BaseModel):
    user_id: int
    code: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


async def generate_login_code(user_id: int) -> str:
    """Called by the bot's /dashboardlogin command handler."""
    code = f"{secrets.randbelow(900000) + 100000}"  # 6-digit code
    await redis_manager.set_json(f"dashboard_login:{user_id}", code, ex=_CODE_TTL_SECONDS)
    return code


@router.post("/verify", response_model=TokenResponse)
async def verify_code(payload: CodeVerifyRequest) -> TokenResponse:
    if payload.user_id != settings.owner_id and payload.user_id not in settings.sudo_users:
        raise HTTPException(status_code=403, detail="Not an authorized dashboard user")

    stored_code = await redis_manager.get_json(f"dashboard_login:{payload.user_id}")
    if not stored_code or stored_code != payload.code:
        raise HTTPException(status_code=401, detail="Invalid or expired code")

    await redis_manager.delete(f"dashboard_login:{payload.user_id}")
    token = create_access_token(payload.user_id)
    return TokenResponse(access_token=token)
