"""tests/test_startup_reconciliation_expiration.py — Test suite for T-024 (Gerbang B).

Verifies:
1. Startup reconciliation of hanging 'publishing' drafts after worker crashes.
2. Drafts with existing Post records are reconciled to 'published'.
3. Stale hanging drafts without Post records are reconciled to 'failed'.
4. 48-hour expiration: unreviewed drafts older than 48h (or past expires_at) marked 'expired'.
5. Approved, scheduled, and published drafts are never expired by the expiration job.
6. WorkerService automatically triggers startup reconciliation on start.
7. Complete audit trail verification.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import get_recent_audit_logs
from app.core.clock import utc_now, utc_now_iso
from app.db.models import Account, Draft, Post
from app.scheduler.reconciliation import (
    expire_stale_drafts,
    run_startup_reconciliation,
)
from app.scheduler.worker import WorkerService


# ---------------------------------------------------------------------------
# 1. Startup Crash Reconciliation of Hanging 'publishing' Drafts
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_startup_reconciles_hanging_publishing_drafts(
    db_session: AsyncSession,
) -> None:
    now = utc_now()
    now_iso = now.isoformat()
    stale_iso = (now - timedelta(minutes=10)).isoformat()

    account = Account(
        threads_user_id="user_rec_1",
        username="reconciliation_tester",
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    # 1. Draft A: Status 'publishing', but Post was already inserted into DB
    draft_a = Draft(
        account_id=account.id,
        prompt_version="p_v1",
        llm_model="none",
        parts='["Text A"]',
        text_hash="hash-a",
        status="publishing",
        updated_at=stale_iso,
    )
    db_session.add(draft_a)
    await db_session.commit()

    post_a = Post(
        draft_id=draft_a.id,
        account_id=account.id,
        threads_media_id="th_media_a",
    )
    db_session.add(post_a)

    # 2. Draft B: Status 'publishing', no Post in DB, updated 10 min ago (Hanging crash)
    draft_b = Draft(
        account_id=account.id,
        prompt_version="p_v1",
        llm_model="none",
        parts='["Text B"]',
        text_hash="hash-b",
        status="publishing",
        updated_at=stale_iso,
    )
    db_session.add(draft_b)

    # 3. Draft C: Status 'publishing', very recent (< 10 seconds ago, active worker)
    draft_c = Draft(
        account_id=account.id,
        prompt_version="p_v1",
        llm_model="none",
        parts='["Text C"]',
        text_hash="hash-c",
        status="publishing",
        updated_at=now_iso,
    )
    db_session.add(draft_c)
    await db_session.commit()

    # Run startup reconciliation (max stale = 300s)
    summary = await run_startup_reconciliation(db_session, max_publishing_stale_seconds=300)

    await db_session.refresh(draft_a)
    await db_session.refresh(draft_b)
    await db_session.refresh(draft_c)

    # Draft A: Corrected to 'published'
    assert draft_a.status == "published"
    assert draft_a.id in summary["reconciled_publishing_ids"]

    # Draft B: Corrected to 'failed' (crash recovery)
    assert draft_b.status == "failed"
    assert "Crash reconciliation" in (draft_b.reject_reason or "")
    assert draft_b.id in summary["reconciled_publishing_ids"]

    # Draft C: Still fresh, NOT marked failed
    assert draft_c.status == "publishing"
    assert draft_c.id not in summary["reconciled_publishing_ids"]

    # Check audit logs
    logs_pub = await get_recent_audit_logs(db_session, limit=10, action="reconcile_crash_published")
    assert len(logs_pub) == 1
    assert logs_pub[0].entity_id == draft_a.id

    logs_fail = await get_recent_audit_logs(db_session, limit=10, action="reconcile_crash_failed")
    assert len(logs_fail) == 1
    assert logs_fail[0].entity_id == draft_b.id


# ---------------------------------------------------------------------------
# 2. 48-Hour Unreviewed Draft Expiration
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_expire_stale_drafts_after_48_hours(
    db_session: AsyncSession,
) -> None:
    now = utc_now()
    now_iso = now.isoformat()
    old_created = (now - timedelta(hours=50)).isoformat()
    fresh_created = (now - timedelta(hours=10)).isoformat()

    # 1. Draft 1: pending_review, created 50 hours ago -> MUST EXPIRE
    d1 = Draft(
        account_id="acc-1",
        prompt_version="p_v1",
        llm_model="gemini-2.5-pro",
        parts=json.dumps([{"text": "Old draft"}]),
        text_hash="h1",
        status="pending_review",
        created_at=old_created,
        expires_at=(now - timedelta(hours=2)).isoformat(),
    )
    # 2. Draft 2: generated, past expires_at -> MUST EXPIRE
    d2 = Draft(
        account_id="acc-1",
        prompt_version="p_v1",
        llm_model="gemini-2.5-pro",
        parts=json.dumps([{"text": "Generated draft"}]),
        text_hash="h2",
        status="generated",
        created_at=old_created,
        expires_at=(now - timedelta(minutes=5)).isoformat(),
    )
    # 3. Draft 3: pending_review, created 10 hours ago -> MUST NOT EXPIRE
    d3 = Draft(
        account_id="acc-1",
        prompt_version="p_v1",
        llm_model="gemini-2.5-pro",
        parts=json.dumps([{"text": "Fresh draft"}]),
        text_hash="h3",
        status="pending_review",
        created_at=fresh_created,
        expires_at=(now + timedelta(hours=38)).isoformat(),
    )
    # 4. Draft 4: approved, created 60 hours ago -> MUST NOT EXPIRE (already approved)
    d4 = Draft(
        account_id="acc-1",
        prompt_version="p_v1",
        llm_model="gemini-2.5-pro",
        parts=json.dumps([{"text": "Approved draft"}]),
        text_hash="h4",
        status="approved",
        created_at=old_created,
    )
    # 5. Draft 5: published, created 100 hours ago -> MUST NOT EXPIRE
    d5 = Draft(
        account_id="acc-1",
        prompt_version="p_v1",
        llm_model="gemini-2.5-pro",
        parts=json.dumps([{"text": "Published post"}]),
        text_hash="h5",
        status="published",
        created_at=old_created,
    )

    db_session.add_all([d1, d2, d3, d4, d5])
    await db_session.commit()

    # Execute expiration
    expired_ids = await expire_stale_drafts(db_session, max_age_hours=48)

    assert d1.id in expired_ids
    assert d2.id in expired_ids
    assert d3.id not in expired_ids
    assert d4.id not in expired_ids
    assert d5.id not in expired_ids

    await db_session.refresh(d1)
    await db_session.refresh(d2)
    await db_session.refresh(d3)
    await db_session.refresh(d4)
    await db_session.refresh(d5)

    assert d1.status == "expired"
    assert "expired" in (d1.reject_reason or "").lower()

    assert d2.status == "expired"
    assert "expired" in (d2.reject_reason or "").lower()

    assert d3.status == "pending_review"
    assert d4.status == "approved"
    assert d5.status == "published"

    # Audit log check
    audit_logs = await get_recent_audit_logs(db_session, limit=10, action="draft_expired")
    assert len(audit_logs) == 2


# ---------------------------------------------------------------------------
# 3. WorkerService Start Triggers Startup Reconciliation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_worker_service_triggers_startup_reconciliation(
    db_session: AsyncSession,
) -> None:
    now = utc_now()
    old_iso = (now - timedelta(hours=50)).isoformat()

    stale_draft = Draft(
        account_id="acc-worker-test",
        prompt_version="p_v1",
        llm_model="gemini-2.5-pro",
        parts='["Stale unreviewed text"]',
        text_hash="worker-test-hash",
        status="pending_review",
        created_at=old_iso,
        expires_at=(now - timedelta(hours=2)).isoformat(),
    )
    db_session.add(stale_draft)
    await db_session.commit()

    worker = WorkerService(worker_id="test-recon-worker", lock_ttl_seconds=30)
    started = await worker.start()
    assert started is True

    try:
        # Verify stale_draft was expired automatically on worker start!
        await db_session.refresh(stale_draft)
        assert stale_draft.status == "expired"
    finally:
        await worker.stop()
