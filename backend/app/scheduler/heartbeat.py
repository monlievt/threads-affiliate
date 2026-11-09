"""app/scheduler/heartbeat.py — Worker heartbeat tracker in system_state."""

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

WORKER_HEARTBEAT_KEY = "last_worker_heartbeat"
DEFAULT_MAX_STALE_SECONDS = 120


async def record_worker_heartbeat(
    session: AsyncSession,
    worker_id: str,
) -> dict[str, Any]:
    """Record worker heartbeat in system_state table."""
    now_iso = utc_now_iso()
    now_ts = time.time()

    payload = {
        "worker_id": worker_id,
        "heartbeat_at": now_iso,
        "timestamp": now_ts,
    }

    record = await session.scalar(
        select(SystemState).where(SystemState.key == WORKER_HEARTBEAT_KEY)
    )

    if record is None:
        session.add(
            SystemState(
                key=WORKER_HEARTBEAT_KEY,
                value=json.dumps(payload),
                updated_at=now_iso,
            )
        )
    else:
        record.value = json.dumps(payload)
        record.updated_at = now_iso

    await session.commit()
    return payload


async def get_worker_heartbeat_info(
    session: AsyncSession,
    max_stale_seconds: int = DEFAULT_MAX_STALE_SECONDS,
) -> dict[str, Any]:
    """Retrieve the latest worker heartbeat and status."""
    record = await session.scalar(
        select(SystemState).where(SystemState.key == WORKER_HEARTBEAT_KEY)
    )

    if record is None or not record.value:
        return {
            "worker_id": None,
            "heartbeat_at": None,
            "age_seconds": None,
            "is_alive": False,
        }

    try:
        data = json.loads(record.value)
        ts = float(data.get("timestamp", 0))
        age_seconds = round(time.time() - ts, 1)
        is_alive = age_seconds <= max_stale_seconds

        return {
            "worker_id": data.get("worker_id"),
            "heartbeat_at": data.get("heartbeat_at"),
            "age_seconds": max(0.0, age_seconds),
            "is_alive": is_alive,
        }
    except Exception as exc:
        log.error("Failed to parse worker heartbeat", error=str(exc))
        return {
            "worker_id": None,
            "heartbeat_at": None,
            "age_seconds": None,
            "is_alive": False,
        }


async def is_worker_alive(
    session: AsyncSession,
    max_stale_seconds: int = DEFAULT_MAX_STALE_SECONDS,
) -> bool:
    """Return True if worker sent a heartbeat within max_stale_seconds."""
    info = await get_worker_heartbeat_info(session, max_stale_seconds)
    return bool(info.get("is_alive", False))
