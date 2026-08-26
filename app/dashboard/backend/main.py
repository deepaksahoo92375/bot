"""
Dashboard Backend (FastAPI).
Exposes REST + WebSocket endpoints consumed by the React frontend.
Run with: uvicorn app.dashboard.backend.main:app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import logger
from app.dashboard.backend.auth import get_current_admin
from app.dashboard.backend.routes import analytics, assistants, auth_routes, broadcast, groups, logs, playlists
from app.db.mongo import mongo
from app.db.redis_client import redis_manager


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await mongo.connect()
    await redis_manager.connect()
    logger.info("Dashboard backend started")
    yield
    await redis_manager.disconnect()
    await mongo.disconnect()
    logger.info("Dashboard backend stopped")


app = FastAPI(title="VC Music Bot Dashboard API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router, prefix="/api/auth", tags=["auth"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"], dependencies=[Depends(get_current_admin)])
app.include_router(assistants.router, prefix="/api/assistants", tags=["assistants"], dependencies=[Depends(get_current_admin)])
app.include_router(playlists.router, prefix="/api/playlists", tags=["playlists"], dependencies=[Depends(get_current_admin)])
app.include_router(broadcast.router, prefix="/api/broadcast", tags=["broadcast"], dependencies=[Depends(get_current_admin)])
app.include_router(groups.router, prefix="/api/groups", tags=["groups"], dependencies=[Depends(get_current_admin)])
app.include_router(logs.router, prefix="/api/logs", tags=["logs"], dependencies=[Depends(get_current_admin)])


@app.get("/health")
async def health() -> dict:
    """Used by Kubernetes readiness probes and the watchdog."""
    return {"status": "ok"}


@app.websocket("/ws/live")
async def live_updates(websocket: WebSocket) -> None:
    """Push live active-chat/queue updates to the dashboard."""
    await websocket.accept()
    try:
        while True:
            active = await redis_manager.get_active_chats()
            await websocket.send_json({"active_chats": active})
            import asyncio
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        logger.debug("Dashboard WebSocket client disconnected")


@app.websocket("/ws/logs")
async def live_logs(websocket: WebSocket) -> None:
    """Streams new log lines as they're written, by tailing the Redis live_logs list."""
    import asyncio
    import json

    from app.dashboard.backend.auth import decode_access_token

    token = websocket.query_params.get("token")
    try:
        user_id = decode_access_token(token) if token else None
        if user_id != settings.owner_id and user_id not in settings.sudo_users:
            await websocket.close(code=4403)
            return
    except Exception:  # noqa: BLE001
        await websocket.close(code=4401)
        return

    await websocket.accept()
    last_seen_count = 0
    try:
        while True:
            total = await redis_manager.client.llen("live_logs")
            if total > last_seen_count:
                new_count = min(total - last_seen_count, 50)
                raw_entries = await redis_manager.client.lrange("live_logs", 0, new_count - 1)
                entries = [json.loads(e) for e in reversed(raw_entries)]
                for entry in entries:
                    await websocket.send_json(entry)
                last_seen_count = total
            await asyncio.sleep(1.5)
    except WebSocketDisconnect:
        logger.debug("Log stream client disconnected")
