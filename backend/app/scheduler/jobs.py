"""app/scheduler/jobs.py — Worker background jobs for planner, heartbeat, and due checks."""

from __future__ import annotations

from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now_iso
from app.core.logging import get_logger
from app.db.models import Draft
from app.scheduler.heartbeat import record_worker_heartbeat
from app.scheduler.lock import renew_worker_lock
from app.scheduler.planner import plan_and_schedule_approved_drafts
from app.threads.token_service import check_and_refresh_all_accounts

log = get_logger(__name__)


async def job_worker_heartbeat_and_lock(
    session: AsyncSession,
    worker_id: str,
    ttl_seconds: int = 60,
) -> bool:
    """Periodic job: records worker heartbeat and renews worker lock."""
    try:
        await record_worker_heartbeat(session, worker_id)
        renewed = await renew_worker_lock(session, worker_id, ttl_seconds=ttl_seconds)
        if not renewed:
            log.warning("Could not renew worker lock, another worker might have taken it", worker_id=worker_id)
        return renewed
    except Exception as exc:
        log.error("Error running worker heartbeat job", error=str(exc))
        return False


async def job_plan_approved_drafts(
    session: AsyncSession,
    account_id: str | None = None,
) -> list[Draft]:
    """Periodic job: finds approved drafts and schedules them into valid slots."""
    try:
        return await plan_and_schedule_approved_drafts(session, account_id=account_id)
    except Exception as exc:
        log.error("Error running draft planner job", error=str(exc))
        return []


async def get_due_scheduled_drafts(
    session: AsyncSession,
    up_to_iso: str | None = None,
) -> list[Draft]:
    """Query scheduled drafts whose scheduled_at timestamp is due."""
    cutoff = up_to_iso or utc_now_iso()
    query = (
        select(Draft)
        .where(
            Draft.status == "scheduled",
            Draft.scheduled_at.isnot(None),
            Draft.scheduled_at <= cutoff,
        )
        .order_by(Draft.scheduled_at.asc())
    )
    result = await session.execute(query)
    return list(result.scalars().all())


async def job_refresh_tokens(
    session: AsyncSession,
    threshold_days: int = 15,
) -> dict[str, Any]:
    """Periodic job: checks accounts and refreshes tokens near expiration."""
    try:
        return await check_and_refresh_all_accounts(session, threshold_days=threshold_days)
    except Exception as exc:
        log.error("Error running token refresher job", error=str(exc))
        return {"error": str(exc)}
