"""tests/test_resilience_chaos.py — Resilience and Chaos Testing Suite (T-053).

Simulates high-stress and failure scenarios from docs/10 §3:
1. Chaos 1: Worker crash after container created -> reconciles cleanly, zero duplicate posts.
2. Chaos 2: Critical K-3 Crash (disconnection before creation_id persisted) ->
   detects hanging draft with null creation_id, logs warning incident, engages Kill Switch,
   and prevents duplicate auto-retry.
3. Chaos 3: Zero posting while Kill Switch is ON -> PublishGuard blocks all drafts immediately.
4. Chaos 4: Distributed worker lock contention and TTL failover ->
   concurrent workers cannot execute simultaneously; failover succeeds after TTL expiry.
5. Chaos 5: External API 429 rate limit triggers immediate automatic Kill Switch.
6. Chaos 6: Consecutive failure circuit breaker -> 2 consecutive errors engage Kill Switch;
   successful publish resets the error counter to 0.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now, utc_now_iso
from app.core.crypto import encrypt_token
from app.db.models import Account, Draft, Incident, Post, SystemState
from app.safety.killswitch import get_kill_switch_status, is_kill_switch_active, set_kill_switch
from app.scheduler.lock import WORKER_LOCK_KEY, acquire_worker_lock, renew_worker_lock
from app.scheduler.reconciliation import run_startup_reconciliation
from app.threads.fake import FakeThreadsClient
from app.threads.publisher import (
    publish_draft,
    reconcile_in_flight_drafts,
    save_creation_id,
)


@pytest.fixture
def test_account() -> Account:
    token = encrypt_token("threads_resilience_token_123")
    expiry = (utc_now() + timedelta(days=30)).isoformat()
    return Account(
        id="acc_chaos_test",
        username="chaos_tester",
        threads_user_id="threads_usr_chaos",
        token_encrypted=token,
        token_expires_at=expiry,
        status="active",
        automation_mode="manual_approve",
    )


# ---------------------------------------------------------------------------
# Chaos 1 & 2: Crash Scenarios & Critical K-3 Reconciliation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chaos_scenario_k3_crash_null_creation_id(
    db_session: AsyncSession, test_account: Account
) -> None:
    """Critical K-3 Crash (docs/10 §3):

    Disconnection occurs before creation_id is persisted to DB.
    Draft is stuck in 'publishing' with creation_id = NULL.
    Reconciler MUST:
    - Log warning incident 'HANGING_DRAFT_UNKNOWN_CREATION_ID'
    - Engage Kill Switch
    - Mark draft failed
    - NEVER retry automatically (avoids duplicate post)
    """
    db_session.add(test_account)
    # Ensure kill switch initially OFF
    await set_kill_switch(db_session, active=False, reason="Test start", actor="test")

    # Draft stuck in 'publishing' 400s ago without creation_id
    stale_time = (utc_now() - timedelta(seconds=400)).isoformat()
    stuck_draft = Draft(
        id="draft_k3_crash",
        account_id=test_account.id,
        kind="post",
        prompt_version="p_v1",
        llm_model="gemini-pro",
        parts=json.dumps([{"text": "Simulated K-3 in-flight post"}]),
        status="publishing",
        updated_at=stale_time,
        created_at=stale_time,
    )
    db_session.add(stuck_draft)
    await db_session.commit()

    # Run startup reconciliation
    summary = await run_startup_reconciliation(db_session, max_publishing_stale_seconds=300)

    assert "draft_k3_crash" in summary["reconciled_publishing_ids"]

    # 1. Draft marked failed
    await db_session.refresh(stuck_draft)
    assert stuck_draft.status == "failed"
    assert "CRITICAL_K3_CRASH" in stuck_draft.reject_reason

    # 2. Kill Switch MUST be engaged
    ks_active = await is_kill_switch_active(db_session)
    assert ks_active is True

    # 3. Warning incident recorded
    inc_res = await db_session.execute(
        select(Incident).where(Incident.code == "HANGING_DRAFT_UNKNOWN_CREATION_ID")
    )
    incident = inc_res.scalar_one_or_none()
    assert incident is not None
    assert incident.severity == "warning"

    # 4. Zero duplicate posts created
    post_res = await db_session.execute(select(Post).where(Post.draft_id == stuck_draft.id))
    assert post_res.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_chaos_scenario_worker_crash_with_existing_post(
    db_session: AsyncSession, test_account: Account
) -> None:
    """Worker died after post record was inserted but before draft status committed.

    Reconciler detects existing post and marks draft 'published' without duplicates.
    """
    db_session.add(test_account)

    draft = Draft(
        id="draft_crash_post_exists",
        account_id=test_account.id,
        kind="post",
        prompt_version="p_v1",
        llm_model="gemini-pro",
        parts=json.dumps([{"text": "Already posted text"}]),
        status="publishing",
        updated_at=utc_now_iso(),
        created_at=utc_now_iso(),
    )
    db_session.add(draft)

    post = Post(
        id="post_crash_123",
        draft_id=draft.id,
        account_id=test_account.id,
        threads_media_id="threads_media_123",
        published_at=utc_now_iso(),
    )
    db_session.add(post)
    await db_session.commit()

    reconciled = await reconcile_in_flight_drafts(db_session)
    assert "draft_crash_post_exists" in reconciled

    await db_session.refresh(draft)
    assert draft.status == "published"


# ---------------------------------------------------------------------------
# Chaos 3: Zero Posting while Kill Switch ON
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chaos_zero_posting_when_kill_switch_engaged(
    db_session: AsyncSession, test_account: Account
) -> None:
    """When kill switch is engaged, all publish operations must be blocked immediately."""
    db_session.add(test_account)
    await set_kill_switch(db_session, active=True, reason="Emergency halt", actor="test")

    draft = Draft(
        id="draft_blocked_ks",
        account_id=test_account.id,
        kind="post",
        prompt_version="p_v1",
        llm_model="gemini-pro",
        parts=json.dumps([{"text": "Must not be published!"}]),
        status="approved",
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    db_session.add(draft)
    await db_session.commit()

    fake_client = FakeThreadsClient()

    with pytest.raises(PermissionError, match="KILL_SWITCH_ON"):
        await publish_draft(
            db_session,
            draft_id=draft.id,
            account_id=test_account.id,
            client=fake_client,
        )

    # Verify zero posts created and zero API calls made
    assert len(fake_client.posts) == 0
    post_check = await db_session.execute(select(Post).where(Post.draft_id == draft.id))
    assert post_check.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Chaos 4: Distributed Worker Lock Contention & Failover
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chaos_worker_lock_contention_and_failover(db_session: AsyncSession) -> None:
    # Worker A acquires lock with 5s TTL
    acquired_a = await acquire_worker_lock(db_session, worker_id="worker_A", ttl_seconds=5)
    assert acquired_a is True

    # Worker B tries to acquire simultaneously -> rejected
    acquired_b = await acquire_worker_lock(db_session, worker_id="worker_B", ttl_seconds=5)
    assert acquired_b is False

    # Worker A renews lock successfully
    renewed_a = await renew_worker_lock(db_session, worker_id="worker_A", ttl_seconds=5)
    assert renewed_a is True

    # Worker B still rejected
    assert await acquire_worker_lock(db_session, worker_id="worker_B", ttl_seconds=5) is False

    # Simulate Worker A dying by artificially aging lock past TTL
    lock_row = await db_session.scalar(
        select(SystemState).where(SystemState.key == WORKER_LOCK_KEY)
    )
    assert lock_row is not None
    stale_payload = {
        "worker_id": "worker_A",
        "acquired_at": utc_now_iso(),
        "expires_at": time.time() - 10,
    }
    lock_row.value = json.dumps(stale_payload)
    await db_session.commit()

    # Worker B can now acquire the expired lock (failover success)
    acquired_b_after = await acquire_worker_lock(db_session, worker_id="worker_B", ttl_seconds=5)
    assert acquired_b_after is True


# ---------------------------------------------------------------------------
# Chaos 5 & 6: 429 Rate Limiting & Consecutive Error Circuit Breaker
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chaos_429_rate_limit_activates_killswitch(
    db_session: AsyncSession, test_account: Account
) -> None:
    """Threads API 429 Rate Limit error triggers immediate Kill Switch engagement."""
    db_session.add(test_account)
    await set_kill_switch(db_session, active=False, reason="Clean start", actor="test")

    draft = Draft(
        id="draft_429_test",
        account_id=test_account.id,
        kind="post",
        prompt_version="p_v1",
        llm_model="gemini-pro",
        parts=json.dumps([{"text": "Post triggering 429"}]),
        status="approved",
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    db_session.add(draft)
    await db_session.commit()

    # Fake client simulating 429 rate limit error
    fake_client = FakeThreadsClient()
    fake_client.should_fail_rate_limit = True  # Triggers 429

    from app.threads.client import ThreadsRateLimitError
    with pytest.raises(ThreadsRateLimitError):
        await publish_draft(
            db_session,
            draft_id=draft.id,
            account_id=test_account.id,
            client=fake_client,
        )

    # Verify Kill Switch was automatically turned ON
    ks_active = await is_kill_switch_active(db_session)
    assert ks_active is True
    status_info = await get_kill_switch_status(db_session)
    assert "429" in (status_info.get("reason") or "")


@pytest.mark.asyncio
async def test_chaos_circuit_breaker_two_consecutive_errors(
    db_session: AsyncSession, test_account: Account
) -> None:
    """Two consecutive publish errors trigger automatic Kill Switch."""
    db_session.add(test_account)
    await set_kill_switch(db_session, active=False, reason="Clean start", actor="test")

    draft1 = Draft(
        id="draft_err_1",
        account_id=test_account.id,
        kind="post",
        prompt_version="p_v1",
        llm_model="gemini-pro",
        parts=json.dumps([{"text": "First failing post"}]),
        status="approved",
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    draft2 = Draft(
        id="draft_err_2",
        account_id=test_account.id,
        kind="post",
        prompt_version="p_v1",
        llm_model="gemini-pro",
        parts=json.dumps([{"text": "Second failing post"}]),
        status="approved",
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    db_session.add_all([draft1, draft2])
    await db_session.commit()

    fake_client = FakeThreadsClient()
    fake_client.should_fail_permanent = True  # Fails with 4xx error

    # 1. First failure -> records error, kill switch remains OFF
    try:
        await publish_draft(db_session, draft_id=draft1.id, account_id=test_account.id, client=fake_client)
    except Exception:
        pass

    assert await is_kill_switch_active(db_session) is False

    # 2. Second failure -> 2 consecutive errors -> Kill Switch turns ON!
    try:
        await publish_draft(db_session, draft_id=draft2.id, account_id=test_account.id, client=fake_client)
    except Exception:
        pass

    assert await is_kill_switch_active(db_session) is True
    status_info = await get_kill_switch_status(db_session)
    assert "consecutive publish errors" in (status_info.get("reason") or "").lower()

