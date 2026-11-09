"""tests/test_governor.py — Tests for rate governor, warmup schedule, active hours, and jitter."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Account, Draft, Post
from app.safety.governor import (
    apply_jitter,
    check_governor_limits,
    is_within_active_hours,
)
from app.safety.warmup import get_warmup_tier


# ---------------------------------------------------------------------------
# 1. Warm-up Tier Progression Tests
# ---------------------------------------------------------------------------
def test_warmup_tier_progression() -> None:
    """Test warm-up table limits progression from Week 1 to Week 5+."""
    start_dt = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)

    # Day 0 (Week 1)
    tier_w1 = get_warmup_tier(start_dt, current_time=start_dt + timedelta(days=2))
    assert tier_w1.week_label == "Week 1"
    assert tier_w1.max_posts_per_day == 2
    assert tier_w1.max_replies_per_day == 3
    assert tier_w1.min_interval_minutes == 240
    assert tier_w1.target_non_affiliate_ratio == 0.40

    # Day 8 (Week 2)
    tier_w2 = get_warmup_tier(start_dt, current_time=start_dt + timedelta(days=8))
    assert tier_w2.week_label == "Week 2"
    assert tier_w2.max_posts_per_day == 3
    assert tier_w2.max_replies_per_day == 5
    assert tier_w2.min_interval_minutes == 180

    # Day 20 (Weeks 3-4)
    tier_w3 = get_warmup_tier(start_dt, current_time=start_dt + timedelta(days=20))
    assert tier_w3.week_label == "Weeks 3-4"
    assert tier_w3.max_posts_per_day == 4
    assert tier_w3.max_replies_per_day == 6
    assert tier_w3.min_interval_minutes == 150

    # Day 35 (Week 5+)
    tier_w5 = get_warmup_tier(start_dt, current_time=start_dt + timedelta(days=35))
    assert tier_w5.week_label == "Week 5+"
    assert tier_w5.max_posts_per_day == 5
    assert tier_w5.max_replies_per_day == 8
    assert tier_w5.min_interval_minutes == 120


def test_hard_limits_never_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that limits are clamped if HARD_MAX_POSTS_PER_DAY is lowered."""
    monkeypatch.setattr(settings, "HARD_MAX_POSTS_PER_DAY", 3)
    start_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # Week 5+ normally allows 5 posts, but must be clamped to 3
    tier = get_warmup_tier(start_dt, current_time=start_dt + timedelta(days=60))
    assert tier.max_posts_per_day == 3


# ---------------------------------------------------------------------------
# 2. Active Hours Tests
# ---------------------------------------------------------------------------
def test_is_within_active_hours() -> None:
    """Test active hours evaluation (09:00 - 21:00 in America/New_York)."""
    est = ZoneInfo("America/New_York")

    # 14:00 EST (active)
    dt_active = datetime(2026, 11, 9, 14, 0, tzinfo=est)
    assert is_within_active_hours(dt_active, tz_name="America/New_York") is True

    # 03:00 EST (inactive / sleeping hours)
    dt_inactive = datetime(2026, 11, 9, 3, 0, tzinfo=est)
    assert is_within_active_hours(dt_inactive, tz_name="America/New_York") is False

    # 09:00 EST (exact start bound -> active)
    dt_start = datetime(2026, 11, 9, 9, 0, tzinfo=est)
    assert is_within_active_hours(dt_start, tz_name="America/New_York") is True

    # 21:00 EST (exact end bound -> inactive)
    dt_end = datetime(2026, 11, 9, 21, 0, tzinfo=est)
    assert is_within_active_hours(dt_end, tz_name="America/New_York") is False


# ---------------------------------------------------------------------------
# 3. Jitter Tests
# ---------------------------------------------------------------------------
def test_apply_jitter_bounds() -> None:
    """Test that jitter produces timestamps within +-20 minutes."""
    base_time = datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc)

    for _ in range(50):
        jittered = apply_jitter(base_time, max_jitter_minutes=20)
        diff_sec = abs((jittered - base_time).total_seconds())
        assert diff_sec <= 20 * 60


# ---------------------------------------------------------------------------
# 4. Governor Limits in DB Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_governor_daily_post_limit(db_session: AsyncSession) -> None:
    """Test that governor blocks after max daily posts is reached."""
    est = ZoneInfo("America/New_York")
    ref_time = datetime(2026, 11, 9, 14, 0, tzinfo=est)  # 14:00 EST
    start_time_iso = ref_time.astimezone(timezone.utc).isoformat()

    account = Account(
        username="gov_tester",
        threads_user_id="user_gov_1",
        timezone="America/New_York",
        active_hours_start=9,
        active_hours_end=21,
        warmup_started_at=start_time_iso,  # Week 1: max 2 posts/day
    )
    db_session.add(account)
    await db_session.commit()

    # Post 1 at 10:00 EST
    p1_time = datetime(2026, 11, 9, 10, 0, tzinfo=est).astimezone(timezone.utc).isoformat()
    d1 = Draft(account_id=account.id, prompt_version="p", llm_model="m", parts="[]", text_hash="h1", status="published")
    db_session.add(d1)
    await db_session.commit()
    post1 = Post(draft_id=d1.id, account_id=account.id, published_at=p1_time)
    db_session.add(post1)

    # Post 2 at 14:30 EST (4.5 hours later)
    p2_time = datetime(2026, 11, 9, 14, 30, tzinfo=est).astimezone(timezone.utc).isoformat()
    d2 = Draft(account_id=account.id, prompt_version="p", llm_model="m", parts="[]", text_hash="h2", status="published")
    db_session.add(d2)
    await db_session.commit()
    post2 = Post(draft_id=d2.id, account_id=account.id, published_at=p2_time)
    db_session.add(post2)
    await db_session.commit()

    # Attempting Post 3 at 19:00 EST (same day) -> Must be blocked (limit is 2 for Week 1)
    attempt_time = datetime(2026, 11, 9, 19, 0, tzinfo=est).astimezone(timezone.utc)
    decision = await check_governor_limits(db_session, account_id=account.id, proposed_time=attempt_time)

    assert decision.allowed is False
    assert "DAILY_POST_LIMIT_REACHED" in (decision.reason or "")
    assert decision.current_posts_today == 2


@pytest.mark.asyncio
async def test_governor_min_interval_violation(db_session: AsyncSession) -> None:
    """Test that governor blocks if minimum gap between posts is violated."""
    est = ZoneInfo("America/New_York")
    account = Account(
        username="interval_tester",
        threads_user_id="user_gov_2",
        timezone="America/New_York",
        active_hours_start=9,
        active_hours_end=21,
        warmup_started_at=datetime(2026, 11, 9, 0, 0, tzinfo=timezone.utc).isoformat(),  # Week 1: min 240 min (4h)
    )
    db_session.add(account)
    await db_session.commit()

    # Post 1 published at 10:00 EST
    p1_time = datetime(2026, 11, 9, 10, 0, tzinfo=est).astimezone(timezone.utc).isoformat()
    d1 = Draft(account_id=account.id, prompt_version="p", llm_model="m", parts="[]", text_hash="h1", status="published")
    db_session.add(d1)
    await db_session.commit()
    post1 = Post(draft_id=d1.id, account_id=account.id, published_at=p1_time)
    db_session.add(post1)
    await db_session.commit()

    # Proposed Post 2 only 1 hour later (11:00 EST) -> Must be blocked (violates 4h interval)
    attempt_early = datetime(2026, 11, 9, 11, 0, tzinfo=est).astimezone(timezone.utc)
    decision_early = await check_governor_limits(db_session, account_id=account.id, proposed_time=attempt_early)

    assert decision_early.allowed is False
    assert "MIN_INTERVAL_VIOLATED" in (decision_early.reason or "")

    # Proposed Post 2 4.5 hours later (14:30 EST) -> Allowed
    attempt_valid = datetime(2026, 11, 9, 14, 30, tzinfo=est).astimezone(timezone.utc)
    decision_valid = await check_governor_limits(db_session, account_id=account.id, proposed_time=attempt_valid)

    assert decision_valid.allowed is True
