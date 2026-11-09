"""app/api/schedule.py — Weekly calendar schedule management with dual timezone and rate governor.

Follows strict safety principles:
1. Dual timezone representation: US Target (America/New_York) and Operator (Asia/Jakarta).
2. Slots must fall strictly within active hours (default 09:00 - 21:00 EST).
3. Spacing between consecutive posts adheres to warmup tier min_interval_minutes.
4. Quotas adhere strictly to WarmupTier.max_posts_per_day.
5. All slot movements require admin session + CSRF token, and append an audit log entry.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import record_audit_log
from app.core.clock import utc_now, utc_now_iso
from app.core.security import get_current_admin, require_csrf
from app.db.models import Account, Draft, Post
from app.db.session import get_db
from app.safety.governor import is_within_active_hours
from app.safety.warmup import get_warmup_tier
from app.schemas.schedule import (
    CalendarDay,
    CalendarResponse,
    CalendarSlot,
    GovernorRulesSummary,
    MoveSlotRequest,
    MoveSlotResponse,
    ValidateSlotRequest,
    ValidateSlotResponse,
)

router = APIRouter(prefix="/api/schedule", tags=["schedule"])

TARGET_TZ_NAME = "America/New_York"
OPERATOR_TZ_NAME = "Asia/Jakarta"


async def _get_or_create_account(session: AsyncSession) -> Account:
    """Fetch the primary active account or create a fallback default."""
    result = await session.execute(select(Account).where(Account.status == "active").limit(1))
    account = result.scalar_one_or_none()
    if account:
        return account

    # Fallback default account
    now = utc_now_iso()
    account = Account(
        id="acc_default",
        username="affiliate_curator",
        display_name="Affiliate Curator",
        country_code="US",
        timezone=TARGET_TZ_NAME,
        active_hours_start=9,
        active_hours_end=21,
        automation_mode="manual_approve",
        warmup_started_at=now,
        status="active",
        created_at=now,
        updated_at=now,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


def _format_time_tz(dt_utc: datetime, tz_name: str, abbr: str) -> str:
    """Convert UTC datetime to target timezone formatted string."""
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    local_dt = dt_utc.astimezone(tz)
    return f"{local_dt.strftime('%H:%M')} {abbr}"


def _get_text_snippet(draft: Draft) -> str:
    """Extract snippet of text from draft parts."""
    if draft.parts:
        try:
            parts = json.loads(draft.parts)
            if parts and isinstance(parts, list) and "text" in parts[0]:
                text = parts[0]["text"]
                return text[:90] + ("..." if len(text) > 90 else "")
        except Exception:
            pass
    return "Draft posting Threads"


@router.get("/calendar", response_model=CalendarResponse)
async def get_weekly_calendar(
    start_date: str | None = Query(default=None, description="Start date YYYY-MM-DD (defaults to current week Monday)"),
    days_count: int = Query(default=7, ge=1, le=14, description="Number of days to show"),
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> CalendarResponse:
    """Get weekly schedule calendar with dual timezone representation and governor bounds."""
    account = await _get_or_create_account(session)
    warmup = get_warmup_tier(account.warmup_started_at)

    target_tz = ZoneInfo(account.timezone or TARGET_TZ_NAME)
    operator_tz = ZoneInfo(OPERATOR_TZ_NAME)

    now_utc = utc_now()
    now_target = now_utc.astimezone(target_tz)

    # Determine start date
    if start_date:
        try:
            start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Format start_date harus YYYY-MM-DD.",
            )
    else:
        # Default to Monday of current week in target timezone
        start_d = now_target.date() - timedelta(days=now_target.weekday())

    end_d = start_d + timedelta(days=days_count)

    # Calculate UTC bounds for query
    start_dt_target = datetime.combine(start_d, time.min, tzinfo=target_tz)
    end_dt_target = datetime.combine(end_d, time.max, tzinfo=target_tz)
    start_utc_iso = start_dt_target.astimezone(timezone.utc).isoformat()
    end_utc_iso = end_dt_target.astimezone(timezone.utc).isoformat()

    # Query scheduled / approved / published drafts
    drafts_q = (
        select(Draft)
        .options(
            selectinload(Draft.niche),
            selectinload(Draft.style),
            selectinload(Draft.product),
        )
        .where(
            Draft.account_id == account.id,
            Draft.status.in_(["scheduled", "approved", "publishing", "published"]),
            Draft.scheduled_at.is_not(None),
            Draft.scheduled_at >= start_utc_iso,
            Draft.scheduled_at <= end_utc_iso,
        )
        .order_by(Draft.scheduled_at.asc())
    )
    res_drafts = await session.execute(drafts_q)
    all_drafts = res_drafts.scalars().all()

    # Query published posts in this window
    posts_q = (
        select(Post)
        .where(
            Post.account_id == account.id,
            Post.published_at >= start_utc_iso,
            Post.published_at <= end_utc_iso,
        )
    )
    res_posts = await session.execute(posts_q)
    all_posts = res_posts.scalars().all()

    # Group drafts by target date YYYY-MM-DD
    drafts_by_date: dict[str, list[CalendarSlot]] = {}
    published_count_by_date: dict[str, int] = {}

    for d in all_drafts:
        if not d.scheduled_at:
            continue
        try:
            dt_utc = datetime.fromisoformat(d.scheduled_at.replace("Z", "+00:00"))
        except Exception:
            continue

        dt_target = dt_utc.astimezone(target_tz)
        target_date_key = dt_target.strftime("%Y-%m-%d")

        slot = CalendarSlot(
            id=d.id,
            draft_id=d.id,
            status=d.status,
            scheduled_at_utc=dt_utc.isoformat(),
            scheduled_at_target=_format_time_tz(dt_utc, TARGET_TZ_NAME, "EST"),
            scheduled_at_operator=_format_time_tz(dt_utc, OPERATOR_TZ_NAME, "WIB"),
            hour_target=dt_target.hour,
            minute_target=dt_target.minute,
            text_snippet=_get_text_snippet(d),
            niche_name=d.niche.name if d.niche else None,
            style_name=d.style.name if d.style else None,
            product_title=d.product.title if d.product else None,
        )
        drafts_by_date.setdefault(target_date_key, []).append(slot)

    for p in all_posts:
        try:
            dt_utc = datetime.fromisoformat(p.published_at.replace("Z", "+00:00"))
            dt_target = dt_utc.astimezone(target_tz)
            k = dt_target.strftime("%Y-%m-%d")
            published_count_by_date[k] = published_count_by_date.get(k, 0) + 1
        except Exception:
            continue

    # Build CalendarDay objects
    calendar_days: list[CalendarDay] = []
    for day_offset in range(days_count):
        cur_date = start_d + timedelta(days=day_offset)
        cur_date_str = cur_date.strftime("%Y-%m-%d")
        day_slots = drafts_by_date.get(cur_date_str, [])
        pub_count = published_count_by_date.get(cur_date_str, 0)
        sched_count = len(day_slots)
        total_used = sched_count + pub_count
        remaining = max(0, warmup.max_posts_per_day - total_used)

        calendar_days.append(
            CalendarDay(
                date=cur_date_str,
                day_name=cur_date.strftime("%A"),
                is_today=cur_date == now_target.date(),
                scheduled_count=sched_count,
                published_count=pub_count,
                max_posts=warmup.max_posts_per_day,
                remaining_quota=remaining,
                is_quota_full=remaining <= 0,
                slots=day_slots,
            )
        )

    governor_summary = GovernorRulesSummary(
        target_timezone=account.timezone or TARGET_TZ_NAME,
        operator_timezone=OPERATOR_TZ_NAME,
        active_hours_start=account.active_hours_start or 9,
        active_hours_end=account.active_hours_end or 21,
        active_hours_label=f"{account.active_hours_start:02d}:00 - {account.active_hours_end:02d}:00 EST",
        operator_active_hours_label="21:00 - 09:00 (+1) WIB",
        min_interval_minutes=warmup.min_interval_minutes,
        warmup_tier_label=warmup.week_label,
        max_posts_per_day=warmup.max_posts_per_day,
    )

    return CalendarResponse(
        start_date=start_d.strftime("%Y-%m-%d"),
        end_date=end_d.strftime("%Y-%m-%d"),
        days=calendar_days,
        governor=governor_summary,
    )


@router.post("/validate-slot", response_model=ValidateSlotResponse)
async def validate_schedule_slot(
    payload: ValidateSlotRequest,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> ValidateSlotResponse:
    """Validate a candidate schedule time against governor rules without changing state."""
    account = await _get_or_create_account(session)
    warmup = get_warmup_tier(account.warmup_started_at)

    try:
        cand_dt = datetime.fromisoformat(payload.candidate_scheduled_at.replace("Z", "+00:00"))
        if cand_dt.tzinfo is None:
            cand_dt = cand_dt.replace(tzinfo=timezone.utc)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Format tanggal candidate_scheduled_at tidak valid.",
        )

    target_tz = ZoneInfo(account.timezone or TARGET_TZ_NAME)
    cand_target = cand_dt.astimezone(target_tz)
    cand_operator = cand_dt.astimezone(ZoneInfo(OPERATOR_TZ_NAME))

    target_str = cand_target.strftime("%Y-%m-%d %H:%M EST")
    operator_str = cand_operator.strftime("%Y-%m-%d %H:%M WIB")

    # 1. Active hours check
    start_hour = account.active_hours_start or 9
    end_hour = account.active_hours_end or 21
    if not (start_hour <= cand_target.hour < end_hour):
        return ValidateSlotResponse(
            valid=False,
            reason=f"Di luar jam aktif audiens US ({start_hour:02d}:00 - {end_hour:02d}:00 EST / 21:00 - 09:00 WIB).",
            target_time_formatted=target_str,
            operator_time_formatted=operator_str,
            is_active_hours=False,
        )

    # 2. Daily Quota check on candidate date
    target_date_str = cand_target.strftime("%Y-%m-%d")
    start_of_day_target = datetime.combine(cand_target.date(), time.min, tzinfo=target_tz)
    end_of_day_target = datetime.combine(cand_target.date(), time.max, tzinfo=target_tz)

    start_utc_iso = start_of_day_target.astimezone(timezone.utc).isoformat()
    end_utc_iso = end_of_day_target.astimezone(timezone.utc).isoformat()

    existing_query = (
        select(Draft)
        .where(
            Draft.account_id == account.id,
            Draft.status.in_(["scheduled", "approved", "publishing", "published"]),
            Draft.scheduled_at >= start_utc_iso,
            Draft.scheduled_at <= end_utc_iso,
        )
    )
    if payload.draft_id:
        existing_query = existing_query.where(Draft.id != payload.draft_id)

    res = await session.execute(existing_query)
    existing_drafts = res.scalars().all()

    if len(existing_drafts) >= warmup.max_posts_per_day:
        return ValidateSlotResponse(
            valid=False,
            reason=f"Batas kuota harian untuk {target_date_str} ({warmup.max_posts_per_day} post/hari) sudah tercapai.",
            target_time_formatted=target_str,
            operator_time_formatted=operator_str,
            is_active_hours=True,
            violates_quota=True,
        )

    # 3. Min interval spacing check
    min_gap_sec = warmup.min_interval_minutes * 60
    for d in existing_drafts:
        if not d.scheduled_at:
            continue
        try:
            d_dt = datetime.fromisoformat(d.scheduled_at.replace("Z", "+00:00"))
            diff_sec = abs((cand_dt - d_dt).total_seconds())
            if diff_sec < min_gap_sec:
                gap_mins = int(diff_sec // 60)
                return ValidateSlotResponse(
                    valid=False,
                    reason=f"Jeda dengan slot lain terlalu dekat ({gap_mins} mnt). Minimal jeda: {warmup.min_interval_minutes} mnt.",
                    target_time_formatted=target_str,
                    operator_time_formatted=operator_str,
                    is_active_hours=True,
                    violates_interval=True,
                )
        except Exception:
            continue

    return ValidateSlotResponse(
        valid=True,
        reason=None,
        target_time_formatted=target_str,
        operator_time_formatted=operator_str,
        is_active_hours=True,
    )


@router.post("/move-slot", response_model=MoveSlotResponse)
async def move_schedule_slot(
    payload: MoveSlotRequest,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> MoveSlotResponse:
    """Move or reschedule a draft slot with strict governor bounds validation."""
    result = await session.execute(select(Draft).where(Draft.id == payload.draft_id))
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draf dengan ID {payload.draft_id!r} tidak ditemukan.",
        )

    if draft.status in ("publishing", "published"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Draf dengan status '{draft.status}' tidak dapat dipindah jadwal.",
        )

    # Validate slot against governor
    val_res = await validate_schedule_slot(
        ValidateSlotRequest(
            draft_id=draft.id,
            candidate_scheduled_at=payload.new_scheduled_at,
        ),
        session=session,
        admin=admin,
    )

    if not val_res.valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Pemindahan slot melanggar aturan governor.",
                "reason": val_res.reason,
            },
        )

    cand_dt = datetime.fromisoformat(payload.new_scheduled_at.replace("Z", "+00:00"))
    if cand_dt.tzinfo is None:
        cand_dt = cand_dt.replace(tzinfo=timezone.utc)

    old_scheduled = draft.scheduled_at
    draft.scheduled_at = cand_dt.isoformat()
    draft.status = "scheduled"
    draft.updated_at = utc_now_iso()
    await session.commit()
    await session.refresh(draft)

    # Log audit event
    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="reschedule_draft",
        entity="drafts",
        entity_id=draft.id,
        detail={
            "old_scheduled_at": old_scheduled,
            "new_scheduled_at": draft.scheduled_at,
            "target_time": val_res.target_time_formatted,
            "operator_time": val_res.operator_time_formatted,
        },
    )

    return MoveSlotResponse(
        success=True,
        draft_id=draft.id,
        new_scheduled_at_utc=draft.scheduled_at,
        new_scheduled_at_target=val_res.target_time_formatted,
        new_scheduled_at_operator=val_res.operator_time_formatted,
        status=draft.status,
        message="Slot jadwal berhasil dipindahkan.",
    )
