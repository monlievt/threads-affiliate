"""app/safety/warmup.py — Gradual account warm-up schedule and progression rules.

Warm-up schedule (from docs/06-SAFETY-COMPLIANCE.md §2):
| Warm-up Age | Max Posts/Day | Max Replies/Day | Min Interval Between Posts | Non-Affiliate Target |
|-------------|---------------|-----------------|----------------------------|----------------------|
| Week 1      | 2             | 3               | 4 hours (240 min)          | >= 40%               |
| Week 2      | 3             | 5               | 3 hours (180 min)          | >= 40%               |
| Weeks 3-4   | 4             | 6               | 2.5 hours (150 min)        | >= 30%               |
| Week 5+     | 5             | 8               | 2 hours (120 min)          | >= 30%               |

Absolute hard limits from config (.env) can NEVER be exceeded regardless of warm-up age:
- HARD_MAX_POSTS_PER_DAY (default: 8)
- HARD_MAX_REPLIES_PER_DAY (default: 10)
"""

from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field

from app.config import settings
from app.core.clock import utc_now


class WarmupTier(BaseModel):
    """Publishing rate limits for a given account age."""

    week_label: str = Field(..., description="E.g. 'Week 1', 'Week 2', 'Weeks 3-4', 'Week 5+'")
    day_number: int = Field(..., description="Day number since warmup started (0-indexed).")
    max_posts_per_day: int = Field(..., description="Max posts allowed per 24h rolling/calendar window.")
    max_replies_per_day: int = Field(..., description="Max system-assisted replies per day.")
    min_interval_minutes: int = Field(..., description="Minimum required gap between two publications.")
    target_non_affiliate_ratio: float = Field(..., description="Target minimum ratio of non-affiliate content.")


def get_warmup_tier(
    warmup_started_at: datetime | str | None,
    current_time: datetime | None = None,
) -> WarmupTier:
    """Calculate the active warm-up limits based on account age.

    Args:
        warmup_started_at: When the account began warm-up (ISO-8601 string or datetime).
                           If None, assumes Week 1 (day 0) for maximum conservatism.
        current_time: Reference current time (defaults to utc_now()).

    Returns:
        WarmupTier clamped by hard configuration limits.
    """
    now = current_time or utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if warmup_started_at is None:
        day_number = 0
    else:
        if isinstance(warmup_started_at, str):
            # Parse ISO string
            try:
                start_dt = datetime.fromisoformat(warmup_started_at.replace("Z", "+00:00"))
            except Exception:
                start_dt = now
        else:
            start_dt = warmup_started_at

        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)

        diff = now - start_dt
        day_number = max(0, diff.days)

    # Determine base tier by day count
    if day_number < 7:
        week_label = "Week 1"
        base_posts = 2
        base_replies = 3
        interval_min = 240  # 4 hours
        ratio = 0.40
    elif day_number < 14:
        week_label = "Week 2"
        base_posts = 3
        base_replies = 5
        interval_min = 180  # 3 hours
        ratio = 0.40
    elif day_number < 28:
        week_label = "Weeks 3-4"
        base_posts = 4
        base_replies = 6
        interval_min = 150  # 2.5 hours
        ratio = 0.30
    else:
        week_label = "Week 5+"
        base_posts = 5
        base_replies = 8
        interval_min = 120  # 2 hours
        ratio = 0.30

    # Strictly clamp by hard limits in settings
    effective_posts = min(base_posts, settings.HARD_MAX_POSTS_PER_DAY)
    effective_replies = min(base_replies, settings.HARD_MAX_REPLIES_PER_DAY)

    return WarmupTier(
        week_label=week_label,
        day_number=day_number,
        max_posts_per_day=effective_posts,
        max_replies_per_day=effective_replies,
        min_interval_minutes=interval_min,
        target_non_affiliate_ratio=ratio,
    )
