"""
Dashboard authentication.
Single-tier admin login: only the bot owner/sudo users (by Telegram user ID)
can authenticate, using a short-lived JWT issued after verifying a login
code sent via the bot itself (see auth_routes.py).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import settings

_ALGORITHM = "HS256"
_TOKEN_EXPIRE_MINUTES = 60 * 12

_bearer_scheme = HTTPBearer()


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.dashboard_secret_key, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> int:
    try:
        payload = jwt.decode(token, settings.dashboard_secret_key, algorithms=[_ALGORITHM])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from e


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> int:
    user_id = decode_access_token(credentials.credentials)
    if user_id != settings.owner_id and user_id not in settings.sudo_users:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for dashboard access")
    return user_id
