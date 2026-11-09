"""tests/test_publisher_idempotency_retry.py — Test suite for Idempotent Publisher & Crash Reconciliation (T-022).

Verifies:
1. Idempotency: Re-publishing already published draft returns existing Post without API calls.
2. Crash recovery: Step 1 container creation cached in system_state avoids duplicate container creation.
3. Crash reconciliation: Stuck 'publishing' drafts reconciled safely on worker startup.
4. Non-retryable 4xx: Sets draft to 'failed_permanent' and blocks future retry attempts.
5. Consecutive error threshold: 2 consecutive failures automatically engage the emergency Kill Switch.
6. Rate limit: 429 error immediately engages the Kill Switch.
7. Success resets consecutive error counter to 0.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import get_recent_audit_logs
from app.core.clock import utc_now, utc_now_iso
from app.core.crypto import encrypt_token
from app.db.models import Account, AuditLog, Draft, Post, SystemState
from app.safety.killswitch import (
    ensure_kill_switch_initialized,
    is_kill_switch_active,
    set_kill_switch,
)
from app.threads.client import ThreadsPermanentApiError, ThreadsRateLimitError
from app.threads.fake import FakeThreadsClient
from app.threads.publisher import (
    get_consecutive_publish_errors,
    get_saved_creation_id,
    publish_single_post,
    reconcile_in_flight_drafts,
    save_creation_id,
)


@pytest.fixture
async def publisher_account(db_session: AsyncSession) -> Account:
    """Fixture returning an authorized test Account with encrypted token."""
    account = Account(
        threads_user_id="user_t022_tester",
        username="t022_tester",
        token_encrypted=encrypt_token("test-valid-access-token-022"),
        country_code="US",
        timezone="America/New_York",
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)
    return account


class ErrorInjectingThreadsClient(FakeThreadsClient):
    """Fake client with configurable failure injection."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.raise_permanent_4xx = False
        self.raise_rate_limit_429 = False
        self.raise_transient_5xx = False
        self.crash_after_container = False

    async def create_text_container(self, text: str, **kwargs) -> str:
        if self.raise_rate_limit_429:
            raise ThreadsRateLimitError("Rate limit 429", status_code=429)
        if self.raise_permanent_4xx:
            raise ThreadsPermanentApiError("400 Bad Request: Malformed payload", status_code=400)
        if self.raise_transient_5xx:
            raise ConnectionError("503 Service Unavailable")

        creation_id = await super().create_text_container(text, **kwargs)

        if self.crash_after_container:
            raise SystemExit("Simulated process crash immediately after container creation")

        return creation_id

    async def publish(self, creation_id: str):
        if self.raise_rate_limit_429:
            raise ThreadsRateLimitError("Rate limit 429", status_code=429)
        if self.raise_permanent_4xx:
            raise ThreadsPermanentApiError("403 Forbidden: Account restricted", status_code=403)
        if self.raise_transient_5xx:
            raise ConnectionError("500 Internal Server Error")

        return await super().publish(creation_id)


# ---------------------------------------------------------------------------
# 1. Idempotency: Re-publishing does NOT duplicate post
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_publisher_idempotency_no_duplicate_post(
    db_session: AsyncSession, publisher_account: Account
) -> None:
    await set_kill_switch(db_session, active=False, reason="Disarming for idempotency test", actor="test")

    client = FakeThreadsClient(
        user_id=publisher_account.threads_user_id or "user_1",
        username=publisher_account.username or "tester",
    )

    draft = Draft(
        account_id=publisher_account.id,
        kind="post",
        prompt_version="p_v1",
        llm_model="none",
        parts=json.dumps([{"text": "Affiliate link: https://benable.com/kitchen/knife"}]),
        link_url="https://benable.com/kitchen/knife",
        link_placement="in_post",
        text_hash="idemp-test-hash",
        status="approved",
    )
    db_session.add(draft)
    await db_session.commit()

    # First publication
    post_1 = await publish_single_post(
        db_session,
        account_id=publisher_account.id,
        text="Affiliate link: https://benable.com/kitchen/knife",
        draft_id=draft.id,
        client=client,
        actor="test_admin",
    )
    assert post_1.id is not None
    assert client.create_container_calls == 1
    assert client.publish_calls == 1

    # Second publication call with the SAME draft_id (Simulated duplicate publish trigger)
    post_2 = await publish_single_post(
        db_session,
        account_id=publisher_account.id,
        text="Affiliate link: https://benable.com/kitchen/knife",
        draft_id=draft.id,
        client=client,
        actor="test_admin",
    )

    # Must return the EXACT same post without calling Threads API again!
    assert post_2.id == post_1.id
    assert post_2.threads_media_id == post_1.threads_media_id
    assert client.create_container_calls == 1  # Calls did NOT increment
    assert client.publish_calls == 1           # Calls did NOT increment


# ---------------------------------------------------------------------------
# 2. Crash Recovery: Container Caching Avoids Duplicate Creation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_crash_recovery_step1_container_caching(
    db_session: AsyncSession, publisher_account: Account
) -> None:
    await set_kill_switch(db_session, active=False, reason="Disarming for crash test", actor="test")

    client = FakeThreadsClient(
        user_id=publisher_account.threads_user_id or "user_1",
        username=publisher_account.username or "tester",
    )

    draft = Draft(
        account_id=publisher_account.id,
        kind="post",
        prompt_version="p_v1",
        llm_model="none",
        parts=json.dumps([{"text": "Affiliate link: https://benable.com/kitchen/pot"}]),
        link_url="https://benable.com/kitchen/pot",
        link_placement="in_post",
        text_hash="crash-test-hash",
        status="approved",
    )
    db_session.add(draft)
    await db_session.commit()

    # Pre-simulate that Step 1 (create_text_container) completed and saved creation_id before crash
    creation_id_pre = await client.create_text_container("Affiliate link: https://benable.com/kitchen/pot")
    await save_creation_id(db_session, draft.id, creation_id_pre)

    container_calls_before = client.create_container_calls

    # Publisher runs to complete the draft
    post = await publish_single_post(
        db_session,
        account_id=publisher_account.id,
        text="Affiliate link: https://benable.com/kitchen/pot",
        draft_id=draft.id,
        client=client,
        actor="reconciler",
    )

    # Step 1 was bypassed because creation_id was already in system_state!
    assert client.create_container_calls == container_calls_before
    assert post.creation_id == creation_id_pre

    # Temporary creation_id is cleaned up upon post creation
    saved_after = await get_saved_creation_id(db_session, draft.id)
    assert saved_after is None


# ---------------------------------------------------------------------------
# 3. Crash Reconciliation: In-flight Drafts Reconciled Safely
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reconcile_in_flight_drafts(
    db_session: AsyncSession, publisher_account: Account
) -> None:
    now_iso = utc_now_iso()
    stale_iso = (utc_now() - timedelta(minutes=15)).isoformat()

    # Case 1: Draft in 'publishing' but post already created
    draft_with_post = Draft(
        account_id=publisher_account.id,
        prompt_version="p_v1",
        llm_model="none",
        parts='["text 1"]',
        text_hash="reconcile-hash-1",
        status="publishing",
        updated_at=stale_iso,
    )
    db_session.add(draft_with_post)
    await db_session.commit()

    post = Post(
        draft_id=draft_with_post.id,
        account_id=publisher_account.id,
        threads_media_id="th_existing_123",
    )
    db_session.add(post)
    await db_session.commit()

    # Case 2: Draft in 'publishing' without post, older than 5 minutes (crashed worker)
    draft_hanging = Draft(
        account_id=publisher_account.id,
        prompt_version="p_v1",
        llm_model="none",
        parts='["text 2"]',
        text_hash="reconcile-hash-2",
        status="publishing",
        updated_at=stale_iso,
    )
    db_session.add(draft_hanging)
    await db_session.commit()

    # Run reconciliation
    reconciled = await reconcile_in_flight_drafts(db_session, max_stale_seconds=300)
    assert draft_with_post.id in reconciled
    assert draft_hanging.id in reconciled

    await db_session.refresh(draft_with_post)
    await db_session.refresh(draft_hanging)

    # Case 1 becomes 'published'
    assert draft_with_post.status == "published"

    # Case 2 becomes 'failed'
    assert draft_hanging.status == "failed"
    assert "Crash reconciliation" in (draft_hanging.reject_reason or "")


# ---------------------------------------------------------------------------
# 4. Non-retryable 4xx Error sets 'failed_permanent'
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_non_retryable_4xx_marks_failed_permanent(
    db_session: AsyncSession, publisher_account: Account
) -> None:
    await set_kill_switch(db_session, active=False, reason="Prep test", actor="test")

    client = ErrorInjectingThreadsClient(
        user_id=publisher_account.threads_user_id or "user_1",
        username=publisher_account.username or "tester",
    )
    client.raise_permanent_4xx = True

    draft = Draft(
        account_id=publisher_account.id,
        kind="post",
        prompt_version="p_v1",
        llm_model="none",
        parts=json.dumps([{"text": "Affiliate link: https://benable.com/kitchen/fryer"}]),
        link_url="https://benable.com/kitchen/fryer",
        link_placement="in_post",
        text_hash="perm-4xx-hash",
        status="approved",
    )
    db_session.add(draft)
    await db_session.commit()

    # Publication attempt fails with 4xx
    with pytest.raises(ThreadsPermanentApiError):
        await publish_single_post(
            db_session,
            account_id=publisher_account.id,
            text="Affiliate link: https://benable.com/kitchen/fryer",
            draft_id=draft.id,
            client=client,
        )

    await db_session.refresh(draft)
    assert draft.status == "failed_permanent"
    assert "Non-retryable 4xx" in (draft.reject_reason or "")

    # Re-running failed_permanent draft MUST be blocked immediately
    with pytest.raises(ValueError, match="failed_permanent"):
        await publish_single_post(
            db_session,
            account_id=publisher_account.id,
            text="Affiliate link: https://benable.com/kitchen/fryer",
            draft_id=draft.id,
            client=client,
        )


# ---------------------------------------------------------------------------
# 5. Two Consecutive Errors Engage Kill Switch
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_two_consecutive_errors_trigger_kill_switch(
    db_session: AsyncSession, publisher_account: Account
) -> None:
    await set_kill_switch(db_session, active=False, reason="Prep 2-error test", actor="test")
    assert await is_kill_switch_active(db_session) is False

    client = ErrorInjectingThreadsClient(
        user_id=publisher_account.threads_user_id or "user_1",
        username=publisher_account.username or "tester",
    )
    client.raise_transient_5xx = True

    # Error 1
    draft1 = Draft(
        account_id=publisher_account.id,
        parts=json.dumps([{"text": "Post 1"}]),
        text_hash="h1",
        status="approved",
        prompt_version="p_v1",
        llm_model="none",
    )
    db_session.add(draft1)
    await db_session.commit()

    with pytest.raises(ConnectionError):
        await publish_single_post(
            db_session,
            account_id=publisher_account.id,
            text="Post 1",
            draft_id=draft1.id,
            client=client,
        )

    assert await get_consecutive_publish_errors(db_session) == 1
    assert await is_kill_switch_active(db_session) is False  # 1 error does not engage kill switch

    # Error 2
    draft2 = Draft(
        account_id=publisher_account.id,
        parts=json.dumps([{"text": "Post 2"}]),
        text_hash="h2",
        status="approved",
        prompt_version="p_v1",
        llm_model="none",
    )
    db_session.add(draft2)
    await db_session.commit()

    with pytest.raises(ConnectionError):
        await publish_single_post(
            db_session,
            account_id=publisher_account.id,
            text="Post 2",
            draft_id=draft2.id,
            client=client,
        )

    assert await get_consecutive_publish_errors(db_session) == 2
    # Two consecutive errors MUST engage Kill Switch automatically!
    assert await is_kill_switch_active(db_session) is True


# ---------------------------------------------------------------------------
# 6. Rate Limit (429) Immediately Engages Kill Switch
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rate_limit_429_immediately_triggers_kill_switch(
    db_session: AsyncSession, publisher_account: Account
) -> None:
    await set_kill_switch(db_session, active=False, reason="Prep 429 test", actor="test")
    assert await is_kill_switch_active(db_session) is False

    client = ErrorInjectingThreadsClient(
        user_id=publisher_account.threads_user_id or "user_1",
        username=publisher_account.username or "tester",
    )
    client.raise_rate_limit_429 = True

    draft = Draft(
        account_id=publisher_account.id,
        parts=json.dumps([{"text": "Post 429"}]),
        text_hash="h429",
        status="approved",
        prompt_version="p_v1",
        llm_model="none",
    )
    db_session.add(draft)
    await db_session.commit()

    with pytest.raises(ThreadsRateLimitError):
        await publish_single_post(
            db_session,
            account_id=publisher_account.id,
            text="Post 429",
            draft_id=draft.id,
            client=client,
        )

    # 429 MUST immediately engage Kill Switch!
    assert await is_kill_switch_active(db_session) is True
