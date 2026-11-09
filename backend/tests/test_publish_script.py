"""tests/test_publish_script.py — Tests for minimal guard and safe post publisher."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_token
from app.db.models import Account, AuditLog, Draft, Post
from app.safety.killswitch import ensure_kill_switch_initialized, set_kill_switch
from app.safety.minimal_guard import check_minimal_guard
from app.threads.fake import FakeThreadsClient
from app.threads.publisher import publish_single_post


@pytest.fixture
async def active_account(db_session: AsyncSession) -> Account:
    """Fixture returning a valid test Account with an encrypted token."""
    account = Account(
        threads_user_id="user_test_777",
        username="test_publisher",
        token_encrypted=encrypt_token("valid_access_token_xyz"),
        country_code="US",
        timezone="America/New_York",
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)
    return account


@pytest.mark.asyncio
async def test_guard_blocks_when_kill_switch_is_on(
    db_session: AsyncSession, active_account: Account
) -> None:
    """Test that minimal guard blocks publishing when kill switch is ON."""
    await ensure_kill_switch_initialized(db_session)
    # Ensure kill switch is ON
    await set_kill_switch(db_session, active=True, reason="Enforcing lock", actor="test")

    decision = await check_minimal_guard(
        db_session,
        account=active_account,
        text="Sample post text",
    )

    assert decision.allowed is False
    assert decision.reason is not None
    assert "KILL_SWITCH_ON" in decision.reason


@pytest.mark.asyncio
async def test_guard_blocks_when_token_is_missing(
    db_session: AsyncSession, active_account: Account
) -> None:
    """Test that minimal guard blocks publishing if account has no token."""
    await set_kill_switch(db_session, active=False, reason="Disarming for test", actor="test")

    active_account.token_encrypted = None
    await db_session.commit()

    decision = await check_minimal_guard(
        db_session,
        account=active_account,
        text="Sample post text",
    )

    assert decision.allowed is False
    assert "TOKEN_MISSING" in (decision.reason or "")


@pytest.mark.asyncio
async def test_guard_blocks_empty_and_excessive_text(
    db_session: AsyncSession, active_account: Account
) -> None:
    """Test that text <= 0 or > 500 characters is rejected by guard."""
    await set_kill_switch(db_session, active=False, reason="Disarming for test", actor="test")

    # Empty text
    decision_empty = await check_minimal_guard(
        db_session,
        account=active_account,
        text="   ",
    )
    assert decision_empty.allowed is False
    assert "TEXT_EMPTY" in (decision_empty.reason or "")

    # Text > 500 characters
    long_text = "x" * 501
    decision_long = await check_minimal_guard(
        db_session,
        account=active_account,
        text=long_text,
    )
    assert decision_long.allowed is False
    assert "TEXT_LENGTH_EXCEEDED" in (decision_long.reason or "")


@pytest.mark.asyncio
async def test_guard_blocks_already_published_draft(
    db_session: AsyncSession, active_account: Account
) -> None:
    """Test idempotency: draft already associated with a post is blocked."""
    await set_kill_switch(db_session, active=False, reason="Disarming for test", actor="test")

    # Create draft & post
    draft = Draft(
        account_id=active_account.id,
        kind="post",
        prompt_version="manual",
        llm_model="none",
        parts='["Existing post"]',
        text_hash="dummy_hash",
        status="published",
    )
    db_session.add(draft)
    await db_session.commit()

    post = Post(
        draft_id=draft.id,
        account_id=active_account.id,
        threads_media_id="th_123",
    )
    db_session.add(post)
    await db_session.commit()

    decision = await check_minimal_guard(
        db_session,
        account=active_account,
        text="Try re-publishing",
        draft_id=draft.id,
    )

    assert decision.allowed is False
    assert "ALREADY_PUBLISHED" in (decision.reason or "")


@pytest.mark.asyncio
async def test_safe_publish_flow_with_fake_client(
    db_session: AsyncSession, active_account: Account
) -> None:
    """Test full successful publication flow using FakeThreadsClient."""
    # Disarm kill switch for this test
    await set_kill_switch(
        db_session,
        active=False,
        reason="Manual operator authorized test post",
        actor="admin",
    )

    fake_client = FakeThreadsClient(
        user_id=active_account.threads_user_id or "user_123",
        username=active_account.username or "test_user",
    )

    post_text = "Found this fantastic desktop cable management organizer. Keeps everything tidy!"

    # Execute publish
    post = await publish_single_post(
        db_session,
        account_id=active_account.id,
        text=post_text,
        client=fake_client,
        actor="test_runner",
    )

    assert post.id is not None
    assert post.threads_media_id is not None
    assert post.creation_id is not None
    assert post.permalink is not None
    assert "threads.net" in post.permalink

    # Verify Draft record was updated to 'published'
    draft = await db_session.scalar(select(Draft).where(Draft.id == post.draft_id))
    assert draft is not None
    assert draft.status == "published"

    # Verify AuditLog was recorded
    audit = await db_session.scalar(
        select(AuditLog).where(AuditLog.entity_id == post.id)
    )
    assert audit is not None
    assert audit.action == "post_published"
    assert audit.actor == "test_runner"

