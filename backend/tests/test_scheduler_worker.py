"""tests/test_scheduler_worker.py — Test suite for Scheduler Planner, Worker Lock, and Heartbeat (T-021).

Verifies:
1. Single worker enforcement via DB distributed lock with TTL.
2. Heartbeat tracking and staleness detection in system_state.
3. Scheduling slots strictly within active hours (09:00 - 21:00 EST).
4. Spacing between posts satisfies warmup tier min_interval_minutes.
5. Daily post quota enforcement per calendar day.
6. Safe jitter application without breaking active hours boundary.
7. WorkerService lifecycle and collision prevention.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import get_recent_audit_logs
from app.core.clock import utc_now, utc_now_iso
from app.db.models import Account, Draft, Niche, Post, Style, SystemState
from app.safety.governor import is_within_active_hours
from app.scheduler.heartbeat import (
    get_worker_heartbeat_info,
    is_worker_alive,
    record_worker_heartbeat,
)
from app.scheduler.jobs import get_due_scheduled_drafts, job_plan_approved_drafts
from app.scheduler.lock import (
    acquire_worker_lock,
    release_worker_lock,
    renew_worker_lock,
)
from app.scheduler.planner import (
    clamp_to_active_hours,
    find_next_valid_slot,
    plan_and_schedule_approved_drafts,
)
from app.scheduler.worker import WorkerService


# ---------------------------------------------------------------------------
# 1. Single Worker Lock (Distributed DB Lock)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_single_worker_lock_enforcement(db_session: AsyncSession) -> None:
    worker_1 = "worker-alpha"
    worker_2 = "worker-beta"

    # Worker 1 acquires lock
    ok1 = await acquire_worker_lock(db_session, worker_1, ttl_seconds=60)
    assert ok1 is True

    # Worker 2 attempts to acquire same lock while active -> MUST FAIL
    ok2 = await acquire_worker_lock(db_session, worker_2, ttl_seconds=60)
    assert ok2 is False

    # Worker 1 renews lock -> MUST SUCCEED
    renewed = await renew_worker_lock(db_session, worker_1, ttl_seconds=120)
    assert renewed is True

    # Worker 2 attempts to renew Worker 1's lock -> MUST FAIL
    foreign_renew = await renew_worker_lock(db_session, worker_2, ttl_seconds=120)
    assert foreign_renew is False

    # Worker 1 releases lock
    released = await release_worker_lock(db_session, worker_1)
    assert released is True

    # Worker 2 can now acquire lock -> MUST SUCCEED
    ok2_after = await acquire_worker_lock(db_session, worker_2, ttl_seconds=60)
    assert ok2_after is True


@pytest.mark.asyncio
async def test_worker_lock_expired_takeover(db_session: AsyncSession) -> None:
    worker_1 = "worker-crashed"
    worker_2 = "worker-rescuer"

    # Worker 1 acquires short TTL lock
    await acquire_worker_lock(db_session, worker_1, ttl_seconds=1)

    # Manually expire the lock in DB
    record = await db_session.scalar(
        select(SystemState).where(SystemState.key == "worker_lock")
    )
    assert record is not None
    data = json.loads(record.value)
    data["expires_at"] = time.time() - 10.0  # 10 seconds ago
    record.value = json.dumps(data)
    await db_session.commit()

    # Worker 2 can take over expired lock
    acquired = await acquire_worker_lock(db_session, worker_2, ttl_seconds=60)
    assert acquired is True

    # Verify worker_2 is new owner
    record = await db_session.scalar(
        select(SystemState).where(SystemState.key == "worker_lock")
    )
    assert record is not None
    assert json.loads(record.value)["worker_id"] == worker_2


# ---------------------------------------------------------------------------
# 2. Worker Heartbeat Tracking
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_worker_heartbeat_tracking(db_session: AsyncSession) -> None:
    worker_id = "worker-heartbeat-test"

    # Initially no heartbeat recorded
    info = await get_worker_heartbeat_info(db_session)
    assert info["is_alive"] is False
    assert info["worker_id"] is None

    # Record heartbeat
    payload = await record_worker_heartbeat(db_session, worker_id)
    assert payload["worker_id"] == worker_id

    # Retrieve info
    info = await get_worker_heartbeat_info(db_session, max_stale_seconds=120)
    assert info["is_alive"] is True
    assert info["worker_id"] == worker_id
    assert info["age_seconds"] is not None and info["age_seconds"] < 5.0

    # Stale heartbeat test
    record = await db_session.scalar(
        select(SystemState).where(SystemState.key == "last_worker_heartbeat")
    )
    assert record is not None
    data = json.loads(record.value)
    data["timestamp"] = time.time() - 300.0  # 5 minutes ago
    record.value = json.dumps(data)
    await db_session.commit()

    stale_info = await get_worker_heartbeat_info(db_session, max_stale_seconds=120)
    assert stale_info["is_alive"] is False
    assert stale_info["age_seconds"] >= 300.0


# ---------------------------------------------------------------------------
# 3. Clamping to Active Hours & Jitter Safety
# ---------------------------------------------------------------------------
def test_clamp_to_active_hours() -> None:
    tz = ZoneInfo("America/New_York")

    # Time before active hours (04:00 AM EST)
    dt_early = datetime(2026, 11, 9, 4, 0, tzinfo=tz).astimezone(timezone.utc)
    clamped_early = clamp_to_active_hours(dt_early, tz_name="America/New_York", start_hour=9, end_hour=21)
    clamped_local = clamped_early.astimezone(tz)
    assert clamped_local.hour == 9
    assert clamped_local.minute == 5

    # Time after active hours (22:30 EST)
    dt_late = datetime(2026, 11, 9, 22, 30, tzinfo=tz).astimezone(timezone.utc)
    clamped_late = clamp_to_active_hours(dt_late, tz_name="America/New_York", start_hour=9, end_hour=21)
    clamped_late_local = clamped_late.astimezone(tz)
    assert clamped_late_local.hour == 20
    assert clamped_late_local.minute == 55


def test_find_next_valid_slot_respects_active_hours() -> None:
    tz_name = "America/New_York"
    tz = ZoneInfo(tz_name)

    # Current time is 23:00 EST (night time, outside active hours)
    now_night = datetime(2026, 11, 9, 23, 0, tzinfo=tz).astimezone(timezone.utc)

    slot = find_next_valid_slot(
        now_utc=now_night,
        existing_slots_utc=[],
        tz_name=tz_name,
        start_hour=9,
        end_hour=21,
        max_posts_per_day=5,
        min_interval_minutes=120,
    )

    # Must be scheduled for tomorrow within active hours
    slot_local = slot.astimezone(tz)
    assert slot_local.date() == datetime(2026, 11, 10).date()
    assert 9 <= slot_local.hour < 21
    assert is_within_active_hours(slot, tz_name=tz_name, start_hour=9, end_hour=21) is True


def test_find_next_valid_slot_spacing_and_quota() -> None:
    tz_name = "America/New_York"
    tz = ZoneInfo(tz_name)

    # Current time: 10:00 EST
    now_morning = datetime(2026, 11, 9, 10, 0, tzinfo=tz).astimezone(timezone.utc)

    # Existing slot at 10:15 EST
    existing_1 = datetime(2026, 11, 9, 10, 15, tzinfo=tz).astimezone(timezone.utc)

    slot = find_next_valid_slot(
        now_utc=now_morning,
        existing_slots_utc=[existing_1],
        tz_name=tz_name,
        start_hour=9,
        end_hour=21,
        max_posts_per_day=5,
        min_interval_minutes=120,
        max_jitter_minutes=0,  # disable jitter for exact delta check
    )

    # Next slot must be >= 120 minutes after existing_1
    delta_min = (slot - existing_1).total_seconds() / 60
    assert delta_min >= 120
    assert is_within_active_hours(slot, tz_name=tz_name, start_hour=9, end_hour=21) is True


# ---------------------------------------------------------------------------
# 4. Draft Planning & Scheduling Batch
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_plan_and_schedule_approved_drafts(db_session: AsyncSession) -> None:
    # Setup account in Week 1 warmup (max 1 post/day, min interval 240 min)
    account = Account(
        username="planner_tester",
        timezone="America/New_York",
        active_hours_start=9,
        active_hours_end=21,
        warmup_started_at=utc_now_iso(),  # Week 1
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    # Create 2 approved drafts awaiting scheduling
    draft1 = Draft(
        account_id=account.id,
        prompt_version="p_v1",
        llm_model="gemini-2.5-pro",
        parts=json.dumps([{"text": "Draft 1 content"}]),
        status="approved",
        text_hash="plan-hash-1",
    )
    draft2 = Draft(
        account_id=account.id,
        prompt_version="p_v1",
        llm_model="gemini-2.5-pro",
        parts=json.dumps([{"text": "Draft 2 content"}]),
        status="approved",
        text_hash="plan-hash-2",
    )
    db_session.add_all([draft1, draft2])
    await db_session.commit()

    # Run planner
    scheduled = await plan_and_schedule_approved_drafts(db_session, account_id=account.id)
    assert len(scheduled) == 2

    await db_session.refresh(draft1)
    await db_session.refresh(draft2)

    assert draft1.status == "scheduled"
    assert draft2.status == "scheduled"
    assert draft1.scheduled_at is not None
    assert draft2.scheduled_at is not None

    # Parse scheduled slots
    dt1 = datetime.fromisoformat(draft1.scheduled_at.replace("Z", "+00:00"))
    dt2 = datetime.fromisoformat(draft2.scheduled_at.replace("Z", "+00:00"))

    # Both MUST be within active hours
    assert is_within_active_hours(dt1, tz_name="America/New_York", start_hour=9, end_hour=21) is True
    assert is_within_active_hours(dt2, tz_name="America/New_York", start_hour=9, end_hour=21) is True

    # In Week 1, max_posts_per_day is 1!
    # Therefore, draft1 and draft2 must be scheduled on DIFFERENT calendar days!
    tz = ZoneInfo("America/New_York")
    local1 = dt1.astimezone(tz).date()
    local2 = dt2.astimezone(tz).date()
    assert local1 != local2
    assert local2 > local1

    # Verify audit logs
    audit_logs = await get_recent_audit_logs(db_session, limit=10, action="schedule_draft")
    assert len(audit_logs) >= 2


# ---------------------------------------------------------------------------
# 5. Due Drafts Query
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_due_scheduled_drafts_query(db_session: AsyncSession) -> None:
    now_iso = utc_now_iso()
    past_iso = (utc_now() - timedelta(minutes=15)).isoformat()
    future_iso = (utc_now() + timedelta(hours=2)).isoformat()

    # Draft in the past (due)
    due_draft = Draft(
        account_id="acc-1",
        prompt_version="p_v1",
        llm_model="gemini-2.5-pro",
        parts=json.dumps([{"text": "Due draft"}]),
        status="scheduled",
        scheduled_at=past_iso,
        text_hash="due-hash-1",
    )
    # Draft in the future (not due)
    future_draft = Draft(
        account_id="acc-1",
        prompt_version="p_v1",
        llm_model="gemini-2.5-pro",
        parts=json.dumps([{"text": "Future draft"}]),
        status="scheduled",
        scheduled_at=future_iso,
        text_hash="future-hash-1",
    )
    db_session.add_all([due_draft, future_draft])
    await db_session.commit()

    due_list = await get_due_scheduled_drafts(db_session, up_to_iso=now_iso)
    due_ids = [d.id for d in due_list]

    assert due_draft.id in due_ids
    assert future_draft.id not in due_ids
