"""app/scheduler/lock.py — Distributed single-worker lock stored in system_state.

Ensures strictly one worker process runs across the entire system.
Uses a time-to-live (TTL) mechanism to prevent deadlocks if a worker crashes.
"""

from __future__ import annotations

import json
import time
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now_iso
from app.core.logging import get_logger
from app.db.models import SystemState

log = get_logger(__name__)

WORKER_LOCK_KEY = "worker_lock"
DEFAULT_LOCK_TTL_SECONDS = 60


async def acquire_worker_lock(
    session: AsyncSession,
    worker_id: str,
    ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS,
) -> bool:
    """Attempt to acquire or re-acquire the global worker lock.

    Returns:
        True if lock was successfully acquired or renewed by worker_id.
        False if held by another active worker.
    """
    now_ts = time.time()
    record = await session.scalar(
        select(SystemState).where(SystemState.key == WORKER_LOCK_KEY)
    )

    if record is not None and record.value:
        try:
            lock_data = json.loads(record.value)
            current_owner = lock_data.get("worker_id")
            expires_at = float(lock_data.get("expires_at", 0))

            # If owned by another worker and still valid (not expired)
            if current_owner != worker_id and expires_at > now_ts:
                log.info(
                    "Worker lock currently held by another worker",
                    active_owner=current_owner,
                    expires_in_sec=round(expires_at - now_ts, 1),
                    candidate_worker=worker_id,
                )
                return False
        except Exception as exc:
            log.warning("Corrupt worker lock record, acquiring fresh lock", error=str(exc))

    # Acquire or take over expired lock
    payload = {
        "worker_id": worker_id,
        "acquired_at": utc_now_iso(),
        "expires_at": now_ts + ttl_seconds,
        "ttl_seconds": ttl_seconds,
    }

    if record is None:
        session.add(
            SystemState(
                key=WORKER_LOCK_KEY,
                value=json.dumps(payload),
                updated_at=utc_now_iso(),
            )
        )
    else:
        record.value = json.dumps(payload)
        record.updated_at = utc_now_iso()

    await session.commit()
    log.info("Worker lock acquired/renewed successfully", worker_id=worker_id, ttl=ttl_seconds)
    return True


async def renew_worker_lock(
    session: AsyncSession,
    worker_id: str,
    ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS,
) -> bool:
    """Renew existing lock if currently owned by worker_id."""
    now_ts = time.time()
    record = await session.scalar(
        select(SystemState).where(SystemState.key == WORKER_LOCK_KEY)
    )

    if record is None or not record.value:
        return False

    try:
        lock_data = json.loads(record.value)
        if lock_data.get("worker_id") != worker_id:
            return False

        lock_data["expires_at"] = now_ts + ttl_seconds
        lock_data["updated_at"] = utc_now_iso()
        record.value = json.dumps(lock_data)
        record.updated_at = utc_now_iso()
        await session.commit()
        return True
    except Exception as exc:
        log.error("Failed to renew worker lock", error=str(exc))
        return False


async def release_worker_lock(
    session: AsyncSession,
    worker_id: str,
) -> bool:
    """Release worker lock if owned by worker_id."""
    record = await session.scalar(
        select(SystemState).where(SystemState.key == WORKER_LOCK_KEY)
    )
    if record is None or not record.value:
        return False

    try:
        lock_data = json.loads(record.value)
        if lock_data.get("worker_id") == worker_id:
            await session.delete(record)
            await session.commit()
            log.info("Worker lock released successfully", worker_id=worker_id)
            return True
        return False
    except Exception as exc:
        log.error("Failed to release worker lock", error=str(exc))
        return False
