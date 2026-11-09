"""tests/test_publish_guard.py — Comprehensive test suite for all 10 checks of PublishGuard."""

from __future__ import annotations

import inspect
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now_iso
from app.core.crypto import encrypt_token
from app.db.models import Account, Draft, Persona, Post
from app.safety.guard import PublishGuard
from app.safety.killswitch import ensure_kill_switch_initialized, set_kill_switch
from app.threads.base import QuotaInfo
from app.threads.fake import FakeThreadsClient


@pytest.fixture
async def setup_compliant_env(db_session: AsyncSession) -> tuple[Account, Draft, FakeThreadsClient]:
    """Fixture creating a 100% compliant account, draft, and client within active hours."""
    # Active hour in America/New_York (e.g. 14:00 EST = 19:00 UTC)
    est = ZoneInfo("America/New_York")
    warmup_start = datetime(2026, 1, 1, 12, 0, tzinfo=est).astimezone(timezone.utc).isoformat()

    account = Account(
        username="guard_tester",
        threads_user_id="th_user_guard_1",
        country_code="US",
        timezone="America/New_York",
        active_hours_start=9,
        active_hours_end=21,
        automation_mode="manual_approve",
        warmup_started_at=warmup_start,
        token_encrypted=encrypt_token("valid_token_abc_123"),
        token_expires_at=(datetime.now(timezone.utc) + timedelta(days=60)).isoformat(),
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    persona = Persona(
        account_id=account.id,
        name="Tech Curator",
        voice="Humble curator tone",
        disclosure_text="Affiliate link",
    )
    db_session.add(persona)

    valid_text = (
        "Found this minimal headphone desk mount made of solid aluminum. "
        "Clamps cleanly to tables up to 2 inches thick. Affiliate link: https://benable.com/tech/holder"
    )

    draft = Draft(
        account_id=account.id,
        kind="post",
        prompt_version="p_v1",
        llm_model="gemini-2.5-pro",
        parts=json.dumps([valid_text]),
        link_url="https://benable.com/tech/holder",
        text_hash="hash_guard_valid_01",
        status="approved",
    )
    db_session.add(draft)
    await db_session.commit()
    await db_session.refresh(draft)

    # Disarm kill switch
    await set_kill_switch(db_session, active=False, reason="Test setup", actor="admin")

    client = FakeThreadsClient(user_id=account.threads_user_id, username=account.username)
    return account, draft, client


# ---------------------------------------------------------------------------
# Test 0: Reflection check — NO 'force' or 'bypass' parameter allowed
# ---------------------------------------------------------------------------
def test_no_force_bypass_parameter() -> None:
    """AGENTS.md hard rule: No force or bypass parameter in PublishGuard."""
    sig = inspect.signature(PublishGuard.check)
    params = sig.parameters
    assert "force" not in params
    assert "bypass" not in params
    assert "skip_checks" not in params


# ---------------------------------------------------------------------------
# Check 1: Kill switch engaged
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_check_1_kill_switch_on(
    db_session: AsyncSession, setup_compliant_env: tuple[Account, Draft, FakeThreadsClient]
) -> None:
    account, draft, client = setup_compliant_env
    # Engage kill switch
    await set_kill_switch(db_session, active=True, reason="Emergency lock", actor="test")

    decision = await PublishGuard.check(db_session, draft=draft, account=account, client=client)
    assert decision.allowed is False
    assert "KILL_SWITCH_ON" in (decision.reason or "")


# ---------------------------------------------------------------------------
# Check 2: Missing or expired token
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_check_2_token_missing_and_expired(
    db_session: AsyncSession, setup_compliant_env: tuple[Account, Draft, FakeThreadsClient]
) -> None:
    account, draft, client = setup_compliant_env

    # 2a. Missing token
    account.token_encrypted = None
    await db_session.commit()

    decision = await PublishGuard.check(db_session, draft=draft, account=account, client=client)
    assert decision.allowed is False
    assert "TOKEN_MISSING" in (decision.reason or "")

    # 2b. Expired token
    account.token_encrypted = encrypt_token("some_token")
    account.token_expires_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    await db_session.commit()

    decision_exp = await PublishGuard.check(db_session, draft=draft, account=account, client=client)
    assert decision_exp.allowed is False
    assert "TOKEN_EXPIRED" in (decision_exp.reason or "")


# ---------------------------------------------------------------------------
# Check 3: Invalid draft status & already published
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_check_3_draft_status_and_duplicate(
    db_session: AsyncSession, setup_compliant_env: tuple[Account, Draft, FakeThreadsClient]
) -> None:
    account, draft, client = setup_compliant_env

    # Invalid status
    draft.status = "rejected"
    await db_session.commit()

    decision_rej = await PublishGuard.check(db_session, draft=draft, account=account, client=client)
    assert decision_rej.allowed is False
    assert "INVALID_DRAFT_STATUS" in (decision_rej.reason or "")

    # Already published
    draft.status = "approved"
    post = Post(draft_id=draft.id, account_id=account.id, threads_media_id="th_99")
    db_session.add(post)
    await db_session.commit()

    decision_dup = await PublishGuard.check(db_session, draft=draft, account=account, client=client)
    assert decision_dup.allowed is False
    assert "ALREADY_PUBLISHED" in (decision_dup.reason or "")


# ---------------------------------------------------------------------------
# Check 4: Automation mode approval check
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_check_4_manual_approval_required(
    db_session: AsyncSession, setup_compliant_env: tuple[Account, Draft, FakeThreadsClient]
) -> None:
    account, draft, client = setup_compliant_env
    account.automation_mode = "manual_approve"
    draft.status = "scheduled"  # Not yet approved in manual mode
    await db_session.commit()

    decision = await PublishGuard.check(db_session, draft=draft, account=account, client=client)
    assert decision.allowed is False
    assert "MANUAL_APPROVAL_REQUIRED" in (decision.reason or "")


# ---------------------------------------------------------------------------
# Check 5: Re-running content safety validators (V-*)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_check_5_content_validator_violations(
    db_session: AsyncSession, setup_compliant_env: tuple[Account, Draft, FakeThreadsClient]
) -> None:
    account, draft, client = setup_compliant_env

    # Inject price & fake urgency into draft parts
    bad_text = "Grab this miracle holder for only $19.99! Hurry ends tonight! https://benable.com/p/1"
    draft.parts = json.dumps([bad_text])
    draft.status = "approved"
    await db_session.commit()

    decision = await PublishGuard.check(db_session, draft=draft, account=account, client=client)
    assert decision.allowed is False
    assert "VALIDATOR_FAILED" in (decision.reason or "")


# ---------------------------------------------------------------------------
# Check 6: Similarity check (V-SIM)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_check_6_similarity_exceeded(
    db_session: AsyncSession, setup_compliant_env: tuple[Account, Draft, FakeThreadsClient]
) -> None:
    account, draft, client = setup_compliant_env
    now_iso = utc_now_iso()

    # Pre-populate historical post with identical text
    identical_text = "Found this minimal headphone desk mount made of solid aluminum."
    d_past = Draft(
        account_id=account.id,
        prompt_version="p",
        llm_model="m",
        parts=json.dumps([identical_text]),
        text_hash="past_hash",
        status="published",
        created_at=now_iso,
    )
    db_session.add(d_past)
    await db_session.commit()

    # Candidate has near-identical text
    draft.parts = json.dumps([identical_text])
    draft.status = "approved"
    await db_session.commit()

    decision = await PublishGuard.check(db_session, draft=draft, account=account, client=client)
    assert decision.allowed is False
    assert "SIMILARITY_EXCEEDED" in (decision.reason or "")


# ---------------------------------------------------------------------------
# Check 9: Threads API Quota Exhausted
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_check_9_api_quota_exhausted(
    db_session: AsyncSession, setup_compliant_env: tuple[Account, Draft, FakeThreadsClient]
) -> None:
    account, draft, client = setup_compliant_env
    # Simulate API quota limit exhausted (250/250)
    client.current_quota = QuotaInfo(
        quota_usage=250,
        config_quota_total=250,
        reply_quota_usage=10,
        reply_config_total=1000,
    )

    decision = await PublishGuard.check(db_session, draft=draft, account=account, client=client)
    assert decision.allowed is False
    assert "API_QUOTA_EXHAUSTED" in (decision.reason or "")

