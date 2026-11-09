"""tests/test_models.py — Tests for SQLAlchemy database models and seed data."""

from __future__ import annotations

import json
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Account,
    AccountSnapshot,
    AuditLog,
    Draft,
    Experiment,
    ExperimentArm,
    Incident,
    JobLock,
    LinkClick,
    LlmUsage,
    Niche,
    Persona,
    Post,
    PostMetric,
    Product,
    Setting,
    Style,
    SystemState,
)
from app.db.seed import seed_initial_styles


@pytest.mark.asyncio
async def test_seed_initial_styles(db_session: AsyncSession) -> None:
    """Test seed_initial_styles populates 5 styles and default system state."""
    # First seed run
    count = await seed_initial_styles(db_session)
    assert count == 5

    # Check styles exist
    styles = (await db_session.scalars(select(Style))).all()
    assert len(styles) == 5
    style_names = {s.name for s in styles}
    expected = {"curator", "quick_review", "tips", "pros_cons", "question"}
    assert style_names == expected

    # Check kill switch default in system_state
    kill_switch = await db_session.scalar(
        select(SystemState).where(SystemState.key == "kill_switch")
    )
    assert kill_switch is not None
    assert kill_switch.value == "on"

    # Idempotency: second seed run should insert 0 new styles
    second_count = await seed_initial_styles(db_session)
    assert second_count == 0


@pytest.mark.asyncio
async def test_account_creation_and_constraints(db_session: AsyncSession) -> None:
    """Test creating an Account and verifying constraints."""
    acc = Account(
        username="threads_affiliate_tester",
        threads_user_id="th_user_123",
        country_code="US",
        timezone="America/New_York",
        automation_mode="manual_approve",
    )
    db_session.add(acc)
    await db_session.commit()
    await db_session.refresh(acc)

    assert acc.id is not None
    assert acc.username == "threads_affiliate_tester"
    assert acc.created_at is not None

    # Duplicate threads_user_id should fail
    dup = Account(
        username="another_user",
        threads_user_id="th_user_123",
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_niche_and_product_relationships(db_session: AsyncSession) -> None:
    """Test Niche and Product relationship and constraints."""
    niche = Niche(
        name="home_kitchen",
        description="Kitchen accessories and organization",
        keywords=json.dumps(["cookware", "kitchen gadgets"]),
    )
    db_session.add(niche)
    await db_session.commit()

    product = Product(
        niche_id=niche.id,
        title="Silicone Pot Strainer Clip",
        benable_url="https://benable.com/example/clip-strainer",
        benefits=json.dumps(["Saves storage space", "Fits any pot size"]),
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    assert product.niche_id == niche.id
    assert product.status == "active"

    # Unique constraint on niche.name
    dup_niche = Niche(name="home_kitchen")
    db_session.add(dup_niche)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_draft_and_post_idempotency(db_session: AsyncSession) -> None:
    """Test Draft to Post relationship and UNIQUE draft_id constraint."""
    acc = Account(username="poster_account")
    db_session.add(acc)
    await db_session.commit()

    draft = Draft(
        account_id=acc.id,
        kind="post",
        prompt_version="p_v1",
        llm_model="gemini-2.5-pro",
        parts=json.dumps(["Check out this ergonomic desk lamp. Link below."]),
        text_hash="dummy_hash_12345",
        status="approved",
    )
    db_session.add(draft)
    await db_session.commit()

    post = Post(
        draft_id=draft.id,
        account_id=acc.id,
        threads_media_id="th_post_999",
        permalink="https://threads.net/@poster/post/999",
    )
    db_session.add(post)
    await db_session.commit()

    # Attempting to publish the same draft twice must fail (posts.draft_id UNIQUE)
    dup_post = Post(
        draft_id=draft.id,
        account_id=acc.id,
        threads_media_id="th_post_1000",
    )
    db_session.add(dup_post)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_audit_log_and_system_state(db_session: AsyncSession) -> None:
    """Test appending to audit_log and writing system_state."""
    log_entry = AuditLog(
        actor="system",
        action="kill_switch_on",
        entity="system_state",
        entity_id="kill_switch",
        detail=json.dumps({"reason": "Test audit record"}),
    )
    db_session.add(log_entry)
    await db_session.commit()

    entry = await db_session.scalar(select(AuditLog).where(AuditLog.action == "kill_switch_on"))
    assert entry is not None
    assert entry.actor == "system"


@pytest.mark.asyncio
async def test_llm_usage_and_job_lock(db_session: AsyncSession) -> None:
    """Test LlmUsage compound primary key and JobLock."""
    usage = LlmUsage(day="2026-11-09", model="gemini-2.5-pro", calls=15)
    db_session.add(usage)

    lock = JobLock(name="publish_due", locked_until="2026-11-09T01:00:00Z", owner="worker_1")
    db_session.add(lock)
    await db_session.commit()

    retrieved_lock = await db_session.scalar(select(JobLock).where(JobLock.name == "publish_due"))
    assert retrieved_lock is not None
    assert retrieved_lock.owner == "worker_1"

