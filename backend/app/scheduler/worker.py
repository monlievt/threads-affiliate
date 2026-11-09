"""app/scheduler/worker.py — APScheduler worker service with distributed lock and heartbeat."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.scheduler.heartbeat import record_worker_heartbeat
from app.scheduler.jobs import (
    get_due_scheduled_drafts,
    job_plan_approved_drafts,
    job_worker_heartbeat_and_lock,
)
from app.scheduler.lock import (
    acquire_worker_lock,
    release_worker_lock,
    renew_worker_lock,
)
from app.scheduler.reconciliation import run_startup_reconciliation

log = get_logger(__name__)


class WorkerService:
    """Single-instance worker service managing periodic jobs and heartbeats."""

    def __init__(
        self,
        worker_id: str | None = None,
        lock_ttl_seconds: int = 60,
        heartbeat_interval_seconds: int = 15,
        planner_interval_seconds: int = 60,
    ) -> None:
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.lock_ttl_seconds = lock_ttl_seconds
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.planner_interval_seconds = planner_interval_seconds

        self._is_running = False
        self._lock_held = False
        self._tasks: list[asyncio.Task[Any]] = []
        self._apscheduler: Any = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def lock_held(self) -> bool:
        return self._lock_held

    async def start(self) -> bool:
        """Attempt to acquire lock and start periodic jobs.

        Returns:
            True if started successfully as the sole active worker.
            False if lock is held by another active worker.
        """
        async with AsyncSessionLocal() as session:
            acquired = await acquire_worker_lock(
                session,
                self.worker_id,
                ttl_seconds=self.lock_ttl_seconds,
            )
            if not acquired:
                log.warning(
                    "Worker lock is held by another instance. Aborting startup.",
                    worker_id=self.worker_id,
                )
                return False

            self._lock_held = True
            await record_worker_heartbeat(session, self.worker_id)
            # Run startup reconciliation and 48h expiration check
            await run_startup_reconciliation(session)

        self._is_running = True
        log.info("Worker started successfully", worker_id=self.worker_id)

        # Try setting up APScheduler if installed
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler

            scheduler = AsyncIOScheduler()
            scheduler.add_job(
                self._run_heartbeat_job,
                "interval",
                seconds=self.heartbeat_interval_seconds,
                id="worker_heartbeat",
                replace_existing=True,
            )
            scheduler.add_job(
                self._run_planner_job,
                "interval",
                seconds=self.planner_interval_seconds,
                id="draft_planner",
                replace_existing=True,
            )
            scheduler.start()
            self._apscheduler = scheduler
            log.info("APScheduler initialized and running", worker_id=self.worker_id)
        except ImportError:
            log.info("APScheduler not installed, running with native asyncio task loops", worker_id=self.worker_id)
            self._tasks.append(asyncio.create_task(self._heartbeat_loop()))
            self._tasks.append(asyncio.create_task(self._planner_loop()))

        return True

    async def stop(self) -> None:
        """Gracefully stop jobs and release lock."""
        self._is_running = False

        if self._apscheduler is not None:
            try:
                self._apscheduler.shutdown(wait=False)
            except Exception as exc:
                log.warning("Error shutting down APScheduler", error=str(exc))
            self._apscheduler = None

        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

        if self._lock_held:
            try:
                async with AsyncSessionLocal() as session:
                    await release_worker_lock(session, self.worker_id)
            except Exception as exc:
                log.error("Failed to release worker lock during shutdown", error=str(exc))
            self._lock_held = False

        log.info("Worker stopped cleanly", worker_id=self.worker_id)

    async def _run_heartbeat_job(self) -> None:
        """Run single heartbeat & lock renewal cycle."""
        async with AsyncSessionLocal() as session:
            renewed = await job_worker_heartbeat_and_lock(
                session,
                self.worker_id,
                ttl_seconds=self.lock_ttl_seconds,
            )
            if not renewed:
                log.warning("Worker lost lock ownership!", worker_id=self.worker_id)
                self._lock_held = False

    async def _run_planner_job(self) -> None:
        """Run single draft planning cycle."""
        if not self._lock_held:
            return
        async with AsyncSessionLocal() as session:
            await job_plan_approved_drafts(session)

    async def _heartbeat_loop(self) -> None:
        """Asyncio fallback loop for heartbeats."""
        while self._is_running:
            try:
                await self._run_heartbeat_job()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("Heartbeat loop error", error=str(exc))

            try:
                await asyncio.sleep(self.heartbeat_interval_seconds)
            except asyncio.CancelledError:
                break

    async def _planner_loop(self) -> None:
        """Asyncio fallback loop for planner."""
        while self._is_running:
            try:
                await self._run_planner_job()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("Planner loop error", error=str(exc))

            try:
                await asyncio.sleep(self.planner_interval_seconds)
            except asyncio.CancelledError:
                break
