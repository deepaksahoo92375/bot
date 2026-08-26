"""
GitHub Actions Workflow Chaining Service.

GitHub Actions jobs have a hard ~6 hour runtime limit. This service:
  1. Tracks how long the current job has been running
  2. A few minutes before the limit, persists a full handoff snapshot to Redis
     (active chats, queues, loop modes) so the NEXT job can resume seamlessly
  3. Triggers the next workflow run via the GitHub REST API (repository_dispatch)
  4. Exits cleanly so the current job doesn't get hard-killed mid-stream

A separate watchdog workflow (see .github/workflows/watchdog.yml) checks
periodically whether a bot run is alive, and restarts the chain if it died
unexpectedly (e.g. chaining failed, Actions outage).
"""
from __future__ import annotations

import asyncio
import time

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.db.redis_client import redis_manager
from app.services.queue_engine import queue_engine

_GITHUB_API_BASE = "https://api.github.com"
_JOB_MAX_RUNTIME_SECONDS = 6 * 60 * 60  # GitHub Actions hard limit


class WorkflowChainer:
    def __init__(self) -> None:
        self._start_time = time.monotonic()
        self._chain_triggered = False
        self._monitor_task: asyncio.Task | None = None

    def start_monitoring(self) -> None:
        self._start_time = time.monotonic()
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Workflow chain monitor started")

    def stop_monitoring(self) -> None:
        if self._monitor_task:
            self._monitor_task.cancel()

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self._start_time

    @property
    def seconds_remaining(self) -> float:
        return _JOB_MAX_RUNTIME_SECONDS - self.elapsed_seconds

    async def _monitor_loop(self) -> None:
        trigger_at = settings.chain_trigger_before_min * 60
        while True:
            try:
                await asyncio.sleep(30)
                if not self._chain_triggered and self.seconds_remaining <= trigger_at:
                    logger.warning(
                        "Approaching job time limit ({}s remaining) — chaining next workflow run",
                        int(self.seconds_remaining),
                    )
                    await self.chain_next_run()
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001
                logger.error("Workflow monitor error: {}", e)

    async def build_handoff_snapshot(self) -> dict:
        """Capture everything the next job needs to resume without audible gaps."""
        active_chats = await redis_manager.get_active_chats()
        snapshot: dict = {"active_chats": {}, "created_at": time.time()}

        for chat_id, data in active_chats.items():
            queue = await queue_engine.get_queue(chat_id)
            snapshot["active_chats"][str(chat_id)] = {
                "assistant": data.get("assistant"),
                "queue": [t.model_dump(mode="json") for t in queue],
            }
        return snapshot

    async def chain_next_run(self) -> None:
        """Persist state and trigger the next workflow run via GitHub API."""
        if self._chain_triggered:
            return
        self._chain_triggered = True

        snapshot = await self.build_handoff_snapshot()
        await redis_manager.save_handoff_state(snapshot)
        logger.info("Handoff state saved | active_chats={}", len(snapshot["active_chats"]))

        if not settings.github_token or not settings.github_repository:
            logger.warning(
                "GITHUB_TOKEN/GITHUB_REPOSITORY not set — cannot auto-trigger next run. "
                "Configure these secrets in your workflow for chaining to work."
            )
            return

        await self._dispatch_workflow()

    async def _dispatch_workflow(self) -> None:
        url = f"{_GITHUB_API_BASE}/repos/{settings.github_repository}/dispatches"
        headers = {
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        payload = {"event_type": "chain_restart", "client_payload": {"triggered_at": time.time()}}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 204:
                logger.info("Next workflow run triggered successfully via repository_dispatch")
            else:
                logger.error(
                    "Failed to trigger next workflow run | status={} body={}",
                    resp.status_code,
                    resp.text,
                )
        except httpx.HTTPError as e:
            logger.error("HTTP error triggering next workflow: {}", e)

    async def resume_from_handoff(self) -> dict | None:
        """Called on startup to check if we're resuming from a chained handoff."""
        state = await redis_manager.load_handoff_state()
        if state:
            logger.info(
                "Resuming from workflow handoff | active_chats={}",
                len(state.get("active_chats", {})),
            )
        return state


workflow_chainer = WorkflowChainer()
