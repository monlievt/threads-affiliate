"""app/experiments/allocator.py — Balanced arm allocation and schedule distributor (T-042).

Enforces scientific fairness rules (docs/07 §2):
1. Balanced allocation across arms: Prioritizes arm with lowest scheduled/drafted count.
2. Anti-clustering / Rotasi niche:
   - In single-day planning, prevents two consecutive posts from the same niche/arm.
3. Randomization of posting hours:
   - Rotates slot hours across days so no arm is systematically biased to morning vs evening.
"""

from __future__ import annotations

import random
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.clock import utc_now, utc_now_iso
from app.db.models import Account, Draft, Experiment, ExperimentArm, Post
from app.safety.governor import is_within_active_hours
from app.safety.warmup import WarmupTier, get_warmup_tier
from app.scheduler.planner import clamp_to_active_hours, find_next_valid_slot


async def select_next_arm_for_generation(
    session: AsyncSession,
    experiment_id: str,
    last_arm_id: str | None = None,
    last_niche_id: str | None = None,
) -> tuple[ExperimentArm | None, str]:
    """Select the best arm to allocate the next draft for content generation.

    Returns (selected_arm, explanation_reason).
    """
    res = await session.execute(
        select(Experiment)
        .options(
            selectinload(Experiment.arms).selectinload(ExperimentArm.drafts),
            selectinload(Experiment.arms).selectinload(ExperimentArm.niche),
            selectinload(Experiment.arms).selectinload(ExperimentArm.style),
        )
        .where(Experiment.id == experiment_id)
    )
    exp = res.scalar_one_or_none()
    if not exp:
        return None, f"Experiment '{experiment_id}' not found."

    if exp.status != "running":
        return None, f"Experiment is in status '{exp.status}', not 'running'."

    if not exp.arms:
        return None, "Experiment has no arms configured."

    # Compute arm stats
    arm_stats: list[dict[str, Any]] = []
    for arm in exp.arms:
        draft_count = len([d for d in (arm.drafts or []) if d.status != "rejected_auto"])
        remaining = arm.target_posts - draft_count
        arm_stats.append({
            "arm": arm,
            "draft_count": draft_count,
            "remaining": remaining,
            "is_last_arm": arm.id == last_arm_id,
            "is_last_niche": arm.niche_id is not None and arm.niche_id == last_niche_id,
        })

    # Filter to arms that still need posts
    eligible = [s for s in arm_stats if s["remaining"] > 0]
    if not eligible:
        return None, "All arms have reached their target post count."

    # Sort primarily by least drafts generated (balanced load)
    min_drafts = min(s["draft_count"] for s in eligible)
    candidates = [s for s in eligible if s["draft_count"] == min_drafts]

    # Anti-streak filter: if possible, avoid picking the same arm or same niche as the previous post
    diverse_candidates = [
        c for c in candidates if not c["is_last_arm"] and not c["is_last_niche"]
    ]
    if diverse_candidates:
        selected_stat = diverse_candidates[0]
        reason = (
            f"Selected arm '{selected_stat['arm'].label}' with lowest progress "
            f"({selected_stat['draft_count']}/{selected_stat['arm'].target_posts}) "
            "and alternating niche/arm rotation."
        )
    else:
        # Fall back to avoiding just the same arm
        different_arm_candidates = [c for c in candidates if not c["is_last_arm"]]
        if different_arm_candidates:
            selected_stat = different_arm_candidates[0]
            reason = (
                f"Selected arm '{selected_stat['arm'].label}' with lowest progress "
                f"({selected_stat['draft_count']}/{selected_stat['arm'].target_posts}) "
                "avoiding same arm back-to-back."
            )
        else:
            selected_stat = candidates[0]
            reason = (
                f"Selected arm '{selected_stat['arm'].label}' with progress "
                f"({selected_stat['draft_count']}/{selected_stat['arm'].target_posts})."
            )

    return selected_stat["arm"], reason


def interleave_drafts_by_arm(drafts: list[Draft]) -> list[Draft]:
    """Interleave drafts from different arms/niches to prevent consecutive clusters.

    Uses round-robin interleaving among arm groups.
    """
    if len(drafts) <= 1:
        return drafts

    # Group by arm_id (or niche_id)
    groups: dict[str, list[Draft]] = {}
    for d in drafts:
        key = d.arm_id or d.niche_id or "unassigned"
        groups.setdefault(key, []).append(d)

    interleaved: list[Draft] = []
    # Pop round-robin from each group
    group_keys = list(groups.keys())
    while any(len(g) > 0 for g in groups.values()):
        for k in group_keys:
            if groups[k]:
                interleaved.append(groups[k].pop(0))

    return interleaved


def randomize_time_in_active_window(
    day_date: datetime.date,
    start_hour: int,
    end_hour: int,
    slot_index: int,
    total_slots_today: int,
    tz: ZoneInfo,
) -> datetime:
    """Assign an evenly distributed and jittered time within the active hours window.

    Ensures arms do not cluster at the same time of day.
    """
    total_active_minutes = (end_hour - start_hour) * 60
    if total_slots_today <= 1:
        segment_center = total_active_minutes // 2
    else:
        step = total_active_minutes / total_slots_today
        segment_center = int(step * slot_index + step / 2)

    # Add random jitter up to +- 20 mins while keeping within window
    jitter = random.randint(-20, 20)
    minute_offset = max(15, min(total_active_minutes - 15, segment_center + jitter))

    hour = start_hour + (minute_offset // 60)
    minute = minute_offset % 60

    dt_local = datetime(
        year=day_date.year,
        month=day_date.month,
        day=day_date.day,
        hour=hour,
        minute=minute,
        tzinfo=tz,
    )
    return dt_local.astimezone(timezone.utc)
