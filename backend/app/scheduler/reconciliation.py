"""app/scheduler/reconciliation.py — Startup reconciliation and 48-hour draft expiration.

Hard Rules (docs/03 §8, docs/09 T-024 — GERBANG B):
1. Hanging 'publishing' drafts checked at startup:
   - If Post already created in DB -> advance status to 'published'.
   - If no Post created and draft is stuck > max_stale_seconds -> mark 'failed'.
2. 48-Hour Review Expiration:
   - Drafts in 'pending_review' or 'generated' older than 48 hours (or past expires_at)
     are automatically marked as 'expired'.
3. Audit Trail: All status reconciliations are recorded in append-only audit log.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_log
from app.core.clock import utc_now, utc_now_iso
from app.core.logging import get_logger
from app.db.models import Draft
from app.threads.publisher import reconcile_in_flight_drafts

log = get_logger(__name__)


async def expire_stale_drafts(
    session: AsyncSession,
    max_age_hours: int = 48,
) -> list[str]:
    """Find unreviewed drafts older than max_age_hours (or past expires_at) and mark them 'expired'.

    Only applies to drafts awaiting review ('pending_review' or 'generated').
    Approved, scheduled, published, or rejected drafts are not affected.
    """
    now = utc_now()
    now_iso = now.isoformat()
    cutoff_dt = now - timedelta(hours=max_age_hours)
    cutoff_iso = cutoff_dt.isoformat()

    # Query unreviewed drafts
    query = (
        select(Draft)
        .where(Draft.status.in_(["pending_review", "generated"]))
    )
    result = await session.execute(query)
    candidates = result.scalars().all()

    expired_ids: list[str] = []

    for draft in candidates:
        is_expired = False

        # Check explicit expires_at timestamp
        if draft.expires_at and draft.expires_at <= now_iso:
            is_expired = True
        # Check fallback created_at age
        elif draft.created_at and draft.created_at <= cutoff_iso:
            is_expired = True

        if is_expired:
            draft.status = "expired"
            draft.reject_reason = f"Draft expired after {max_age_hours}h awaiting review without approval."
            draft.updated_at = utc_now_iso()
            expired_ids.append(draft.id)

            await record_audit_log(
                session,
                actor="reconciler",
                action="draft_expired",
                entity="drafts",
                entity_id=draft.id,
                detail={
                    "created_at": draft.created_at,
                    "expires_at": draft.expires_at,
                    "max_age_hours": max_age_hours,
                },
            )

    if expired_ids:
        await session.commit()
        log.info(
            "Expired stale unreviewed drafts (>48h)",
            count=len(expired_ids),
            draft_ids=expired_ids,
        )

    return expired_ids


async def run_startup_reconciliation(
    session: AsyncSession,
    max_publishing_stale_seconds: int = 300,
    max_unreviewed_age_hours: int = 48,
) -> dict[str, Any]:
    """Execute complete startup reconciliation checklist.

    1. Reconcile hanging 'publishing' drafts from previous unexpected crashes.
    2. Expire unreviewed drafts older than 48 hours.
    """
    log.info("Starting system startup reconciliation...")

    # 1. Reconcile hanging publishing drafts
    reconciled_publishing = await reconcile_in_flight_drafts(
        session,
        max_stale_seconds=max_publishing_stale_seconds,
    )

    # 2. Expire stale unreviewed drafts
    expired_drafts = await expire_stale_drafts(
        session,
        max_age_hours=max_unreviewed_age_hours,
    )

    summary = {
        "reconciled_publishing_count": len(reconciled_publishing),
        "reconciled_publishing_ids": reconciled_publishing,
        "expired_drafts_count": len(expired_drafts),
        "expired_draft_ids": expired_drafts,
    }

    log.info("Startup reconciliation completed successfully", **summary)
    return summary
