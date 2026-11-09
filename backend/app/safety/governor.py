"""app/safety/governor.py — Rate governor, active hours enforcement, and slot jittering.

Enforces:
1. Active hours in target timezone (default 09:00 - 21:00 target local time)
2. Daily post quotas strictly derived from WarmupTier and clamped by HARD_MAX_POSTS_PER_DAY
3. Minimum gap between consecutive posts (e.g. 2 to 4 hours)
4. Random time jitter (+- 20 minutes) to eliminate mechanical posting patterns
"""

from __future__ import annotations

import random
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now
from app.core.logging import get_logger
from app.db.models import Account, Post
from app.safety.warmup import WarmupTier, get_warmup_tier

logger = get_logger(__name__)


class GovernorDecision(BaseModel):
    """Result of governor limit check."""

    allowed: bool
    reason: str | None = None
    current_posts_today: int = 0
    max_posts_today: int = 0
    min_interval_minutes: int = 0
    seconds_since_last_post: float | None = None


def is_within_active_hours(
    dt: datetime,
    tz_name: str = "America/New_York",
    start_hour: int = 9,
    end_hour: int = 21,
) -> bool:
    """Return True if datetime falls within active hours in the target local timezone.

    Default: 09:00 to 21:00 in target timezone (e.g. US/Eastern).
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    try:
        target_tz = ZoneInfo(tz_name)
    except Exception:
        target_tz = ZoneInfo("America/New_York")

    local_dt = dt.astimezone(target_tz)
    return start_hour <= local_dt.hour < end_hour


def apply_jitter(
    scheduled_dt: datetime,
    max_jitter_minutes: int = 20,
) -> datetime:
    """Apply a random offset between -max_jitter_minutes and +max_jitter_minutes.

    Avoids exact mechanical minute-aligned posts.
    """
    jitter_sec = random.randint(-max_jitter_minutes * 60, max_jitter_minutes * 60)
    return scheduled_dt + timedelta(seconds=jitter_sec)


def get_target_day_bounds_utc(
    ref_dt_utc: datetime,
    tz_name: str = "America/New_York",
) -> tuple[str, str]:
    """Calculate the UTC start and end ISO-8601 strings for the local calendar day of ref_dt_utc."""
    if ref_dt_utc.tzinfo is None:
        ref_dt_utc = ref_dt_utc.replace(tzinfo=timezone.utc)

    try:
        target_tz = ZoneInfo(tz_name)
    except Exception:
        target_tz = ZoneInfo("America/New_York")

    local_dt = ref_dt_utc.astimezone(target_tz)
    local_start = datetime.combine(local_dt.date(), time.min, tzinfo=target_tz)
    local_end = datetime.combine(local_dt.date(), time.max, tzinfo=target_tz)

    utc_start_iso = local_start.astimezone(timezone.utc).isoformat()
    utc_end_iso = local_end.astimezone(timezone.utc).isoformat()
    return utc_start_iso, utc_end_iso


async def check_governor_limits(
    session: AsyncSession,
    *,
    account_id: str,
    proposed_time: datetime | None = None,
) -> GovernorDecision:
    """Check whether a publication is permitted under current governor and warm-up rules.

    Evaluates:
    1. Active local hours in account target timezone
    2. Daily limit for the current warm-up tier
    3. Minimum interval gap since the most recent post
    """
    now_utc = proposed_time or utc_now()
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    account = await session.scalar(select(Account).where(Account.id == account_id))
    if not account:
        return GovernorDecision(allowed=False, reason=f"Account {account_id!r} not found.")

    tz_name = account.timezone or "America/New_York"
    start_hour = account.active_hours_start
    end_hour = account.active_hours_end

    # 1. Check active hours in target timezone
    if not is_within_active_hours(now_utc, tz_name=tz_name, start_hour=start_hour, end_hour=end_hour):
        return GovernorDecision(
            allowed=False,
            reason=f"OUTSIDE_ACTIVE_HOURS: Proposed time falls outside active hours ({start_hour:02d}:00-{end_hour:02d}:00 in {tz_name}).",
        )

    # 2. Warmup tier calculation
    tier: WarmupTier = get_warmup_tier(account.warmup_started_at, now_utc)

    # 3. Check daily post count in target calendar day
    start_utc_iso, end_utc_iso = get_target_day_bounds_utc(now_utc, tz_name=tz_name)
    stmt_count = (
        select(Post)
        .where(
            Post.account_id == account_id,
            Post.published_at >= start_utc_iso,
            Post.published_at <= end_utc_iso,
        )
    )
    posts_today = (await session.scalars(stmt_count)).all()
    count_today = len(posts_today)

    if count_today >= tier.max_posts_per_day:
        return GovernorDecision(
            allowed=False,
            reason=f"DAILY_POST_LIMIT_REACHED: Already published {count_today}/{tier.max_posts_per_day} posts today ({tier.week_label}).",
            current_posts_today=count_today,
            max_posts_today=tier.max_posts_per_day,
            min_interval_minutes=tier.min_interval_minutes,
        )

    # 4. Check minimum interval from last post
    stmt_last = (
        select(Post)
        .where(Post.account_id == account_id)
        .order_by(Post.published_at.desc())
        .limit(1)
    )
    last_post = await session.scalar(stmt_last)
    seconds_since_last: float | None = None

    if last_post and last_post.published_at:
        try:
            last_dt = datetime.fromisoformat(last_post.published_at.replace("Z", "+00:00"))
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            delta = now_utc - last_dt
            seconds_since_last = delta.total_seconds()
            required_seconds = tier.min_interval_minutes * 60

            if seconds_since_last < required_seconds:
                remaining_wait = int((required_seconds - seconds_since_last) / 60)
                return GovernorDecision(
                    allowed=False,
                    reason=f"MIN_INTERVAL_VIOLATED: Minimum gap is {tier.min_interval_minutes} min; only {int(seconds_since_last / 60)} min elapsed (wait {remaining_wait} min more).",
                    current_posts_today=count_today,
                    max_posts_today=tier.max_posts_per_day,
                    min_interval_minutes=tier.min_interval_minutes,
                    seconds_since_last_post=seconds_since_last,
                )
        except Exception as exc:
            logger.warning("Could not parse last post published_at timestamp", error=str(exc))

    return GovernorDecision(
        allowed=True,
        current_posts_today=count_today,
        max_posts_today=tier.max_posts_per_day,
        min_interval_minutes=tier.min_interval_minutes,
        seconds_since_last_post=seconds_since_last,
    )

