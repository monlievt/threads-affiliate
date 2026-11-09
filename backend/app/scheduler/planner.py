"""app/scheduler/planner.py — Draft scheduling planner with active hours, interval spacing, and jitter.

Enforces:
1. Slots strictly within active local hours in account timezone (default 09:00 - 21:00 EST).
2. Spacing between consecutive posts adheres to warmup tier min_interval_minutes.
3. Daily quota per calendar day adheres to warmup tier max_posts_per_day.
4. Random jitter (+- 15 min) applied without violating active hours boundary.
"""

from __future__ import annotations

import random
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_log
from app.core.clock import utc_now, utc_now_iso
from app.core.logging import get_logger
from app.db.models import Account, Draft, Post
from app.safety.governor import is_within_active_hours
from app.safety.warmup import WarmupTier, get_warmup_tier

log = get_logger(__name__)


def clamp_to_active_hours(
    dt_utc: datetime,
    tz_name: str = "America/New_York",
    start_hour: int = 9,
    end_hour: int = 21,
) -> datetime:
    """Ensure a UTC datetime falls strictly inside target local active hours.

    If before start_hour, clamp to start_hour:05 local.
    If at or after end_hour, clamp to (end_hour - 1):55 local.
    """
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)

    try:
        target_tz = ZoneInfo(tz_name)
    except Exception:
        target_tz = ZoneInfo("America/New_York")

    local_dt = dt_utc.astimezone(target_tz)

    if local_dt.hour < start_hour:
        clamped_local = local_dt.replace(hour=start_hour, minute=5, second=0, microsecond=0)
        return clamped_local.astimezone(timezone.utc)

    if local_dt.hour >= end_hour:
        clamped_local = local_dt.replace(hour=end_hour - 1, minute=55, second=0, microsecond=0)
        return clamped_local.astimezone(timezone.utc)

    return dt_utc


def find_next_valid_slot(
    now_utc: datetime,
    existing_slots_utc: list[datetime],
    tz_name: str = "America/New_York",
    start_hour: int = 9,
    end_hour: int = 21,
    max_posts_per_day: int = 5,
    min_interval_minutes: int = 120,
    max_jitter_minutes: int = 15,
) -> datetime:
    """Calculate the next available publication slot obeying active hours, daily limits, and intervals."""
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    try:
        target_tz = ZoneInfo(tz_name)
    except Exception:
        target_tz = ZoneInfo("America/New_York")

    # Start looking from at least 10 minutes in the future
    candidate_utc = now_utc + timedelta(minutes=10)

    # Sort existing slots
    sorted_slots = sorted([s if s.tzinfo else s.replace(tzinfo=timezone.utc) for s in existing_slots_utc])

    for _ in range(30):  # Safety bound: search up to 30 days ahead
        candidate_local = candidate_utc.astimezone(target_tz)

        # 1. If before active hours today, move to start_hour
        if candidate_local.hour < start_hour:
            candidate_local = candidate_local.replace(hour=start_hour, minute=0, second=0, microsecond=0)
            candidate_utc = candidate_local.astimezone(timezone.utc)
            candidate_local = candidate_utc.astimezone(target_tz)

        # 2. If at or past active hours today, move to tomorrow morning
        if candidate_local.hour >= end_hour:
            tomorrow_date = candidate_local.date() + timedelta(days=1)
            candidate_local = datetime.combine(tomorrow_date, time(hour=start_hour, minute=0), tzinfo=target_tz)
            candidate_utc = candidate_local.astimezone(timezone.utc)
            candidate_local = candidate_utc.astimezone(target_tz)

        # 3. Check daily post count on candidate calendar date
        current_date = candidate_local.date()
        day_slots = [
            s for s in sorted_slots
            if s.astimezone(target_tz).date() == current_date
        ]

        if len(day_slots) >= max_posts_per_day:
            # Day quota full, advance to next day morning
            next_date = current_date + timedelta(days=1)
            candidate_local = datetime.combine(next_date, time(hour=start_hour, minute=0), tzinfo=target_tz)
            candidate_utc = candidate_local.astimezone(timezone.utc)
            continue

        # 4. Check minimum interval from the latest slot on the candidate day
        if day_slots:
            last_day_slot = day_slots[-1]
            earliest_allowed = last_day_slot + timedelta(minutes=min_interval_minutes)
            if candidate_utc < earliest_allowed:
                candidate_utc = earliest_allowed
                candidate_local = candidate_utc.astimezone(target_tz)
                # If pushed past end_hour, loop will roll over to tomorrow
                if candidate_local.hour >= end_hour:
                    continue

        # 5. Apply random jitter (+- max_jitter_minutes)
        jitter_minutes = random.randint(-max_jitter_minutes, max_jitter_minutes)
        jittered_utc = candidate_utc + timedelta(minutes=jitter_minutes)

        # Ensure jittered slot is still in the future and inside active hours
        if jittered_utc <= now_utc + timedelta(minutes=5):
            jittered_utc = candidate_utc + timedelta(minutes=5)

        clamped_utc = clamp_to_active_hours(
            jittered_utc,
            tz_name=tz_name,
            start_hour=start_hour,
            end_hour=end_hour,
        )

        # Final verification
        if is_within_active_hours(clamped_utc, tz_name=tz_name, start_hour=start_hour, end_hour=end_hour):
            return clamped_utc

        # Fallback to candidate_utc if clamping failed
        candidate_utc += timedelta(minutes=30)

    # Fallback to tomorrow morning if loop exhausted
    tomorrow = (now_utc.astimezone(target_tz) + timedelta(days=1)).date()
    fallback_local = datetime.combine(tomorrow, time(hour=start_hour, minute=15), tzinfo=target_tz)
    return fallback_local.astimezone(timezone.utc)


async def plan_and_schedule_approved_drafts(
    session: AsyncSession,
    account_id: str | None = None,
    actor: str = "scheduler",
) -> list[Draft]:
    """Find all approved drafts awaiting scheduling and assign valid future slots.

    Updates draft:
    - status = 'scheduled'
    - scheduled_at = slot_iso
    - records audit log entry
    """
    now = utc_now()

    # 1. Load account settings
    acc_query = select(Account)
    if account_id:
        acc_query = acc_query.where(Account.id == account_id)
    acc_res = await session.execute(acc_query.limit(1))
    account = acc_res.scalar_one_or_none()

    tz_name = account.timezone if account else "America/New_York"
    start_hour = account.active_hours_start if account else 9
    end_hour = account.active_hours_end if account else 21
    warmup_started = account.warmup_started_at if account else None

    tier: WarmupTier = get_warmup_tier(warmup_started, now)
    max_posts_per_day = tier.max_posts_per_day
    min_interval = tier.min_interval_minutes

    # 2. Collect existing scheduled drafts and recent published posts
    scheduled_res = await session.execute(
        select(Draft.scheduled_at).where(
            Draft.status == "scheduled",
            Draft.scheduled_at.isnot(None),
        )
    )
    scheduled_strings = [r for r in scheduled_res.scalars().all() if r]

    published_res = await session.execute(
        select(Post.published_at).where(
            Post.published_at.isnot(None),
        ).order_by(Post.published_at.desc()).limit(20)
    )
    published_strings = [r for r in published_res.scalars().all() if r]

    existing_slots: list[datetime] = []
    for s in scheduled_strings + published_strings:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            existing_slots.append(dt)
        except Exception:
            pass

    # 3. Fetch approved drafts awaiting scheduling
    drafts_query = (
        select(Draft)
        .where(
            Draft.status == "approved",
            Draft.scheduled_at.is_(None),
        )
        .order_by(Draft.reviewed_at.asc(), Draft.created_at.asc())
    )
    if account_id:
        drafts_query = drafts_query.where(Draft.account_id == account_id)

    drafts_res = await session.execute(drafts_query)
    approved_drafts = drafts_res.scalars().all()

    if not approved_drafts:
        return []

    scheduled_drafts: list[Draft] = []

    for draft in approved_drafts:
        slot = find_next_valid_slot(
            now_utc=now,
            existing_slots_utc=existing_slots,
            tz_name=tz_name,
            start_hour=start_hour,
            end_hour=end_hour,
            max_posts_per_day=max_posts_per_day,
            min_interval_minutes=min_interval,
        )

        slot_iso = slot.isoformat()
        draft.status = "scheduled"
        draft.scheduled_at = slot_iso
        draft.updated_at = utc_now_iso()

        existing_slots.append(slot)
        scheduled_drafts.append(draft)

        await record_audit_log(
            session,
            actor=actor,
            action="schedule_draft",
            entity="drafts",
            entity_id=draft.id,
            detail={
                "scheduled_at": slot_iso,
                "warmup_week": tier.week,
                "target_tz": tz_name,
            },
        )

    await session.commit()
    for d in scheduled_drafts:
        await session.refresh(d)

    log.info(
        "Scheduled approved drafts",
        count=len(scheduled_drafts),
        earliest=scheduled_drafts[0].scheduled_at if scheduled_drafts else None,
    )
    return scheduled_drafts
