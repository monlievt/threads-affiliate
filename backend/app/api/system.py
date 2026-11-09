"""app/api/system.py — System health, kill switch, and audit endpoints.

Endpoints:
- GET /health: Public liveness and status check
- GET /api/system/kill-switch: Current kill switch status (authenticated admin)
- POST /api/system/kill-switch: Toggle kill switch state (authenticated admin + CSRF)
- GET /api/system/audit-logs: Retrieve recent audit logs (authenticated admin)
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.audit import get_recent_audit_logs, record_audit_log
from app.core.clock import utc_now, utc_now_iso
from app.core.security import get_current_admin, require_csrf
from app.db.models import Account, AuditLog, Incident, Post
from app.db.session import AsyncSessionLocal, check_db_connection, get_db
from app.safety.killswitch import (
    get_kill_switch_status,
    is_kill_switch_active,
    set_kill_switch,
)
from app.scheduler.heartbeat import get_worker_heartbeat_info
from app.schemas.settings import (
    AccountSettingsResponse,
    AccountSettingsUpdate,
    AuditLogResponse,
    FullAutoCriterion,
    FullAutoEligibilityResponse,
    IncidentResolveRequest,
    IncidentResponse,
)
from app.threads.token_service import get_token_status

router = APIRouter(tags=["system"])


class KillSwitchToggleRequest(BaseModel):
    """Payload for engaging or disarming the emergency kill switch."""

    active: bool = Field(..., description="True to engage (stop publishing); False to disarm (allow).")
    reason: str = Field(..., min_length=3, description="Mandatory reason for audit trail.")


# ---------------------------------------------------------------------------
# Public Health Check
# ---------------------------------------------------------------------------
@router.get("/health")
async def health_check() -> JSONResponse:
    """Return system health status.

    - DB reachability is verified via SELECT 1.
    - Kill switch state is read from system_state table (or env fallback).
    - Returns HTTP 200 for ok/degraded; HTTP 503 for down.
    """
    db_ok = await check_db_connection()
    db_status = "ok" if db_ok else "error"

    kill_switch_status = "on"
    hb_age_sec: float | None = None
    token_valid: bool | None = None

    if db_ok:
        try:
            async with AsyncSessionLocal() as session:
                active = await is_kill_switch_active(session)
                kill_switch_status = "on" if active else "off"
                hb_info = await get_worker_heartbeat_info(session)
                hb_age_sec = hb_info.get("age_seconds")

                acc_res = await session.execute(
                    select(Account).where(Account.token_encrypted.isnot(None)).limit(1)
                )
                acc = acc_res.scalar_one_or_none()
                if acc:
                    t_status = get_token_status(acc)
                    token_valid = t_status["valid"]
        except Exception:
            kill_switch_status = "on" if settings.KILL_SWITCH_ON_START else "off"
    else:
        kill_switch_status = "on" if settings.KILL_SWITCH_ON_START else "off"

    overall = "ok" if db_ok else "down"
    http_status = 200 if db_ok else 503

    payload = {
        "status": overall,
        "db": db_status,
        "worker_heartbeat_age_sec": hb_age_sec,
        "token_valid": token_valid,
        "kill_switch": kill_switch_status,
        "quota_today": None,
    }

    return JSONResponse(content=payload, status_code=http_status)


# ---------------------------------------------------------------------------
# Admin Kill Switch Control
# ---------------------------------------------------------------------------
@router.get("/api/system/kill-switch")
async def get_kill_switch(
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> dict[str, Any]:
    """Retrieve current kill switch status and reason."""
    return await get_kill_switch_status(session)


@router.post("/api/system/kill-switch")
async def toggle_kill_switch(
    payload: KillSwitchToggleRequest,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> dict[str, Any]:
    """Engage or disarm the global kill switch (requires admin + CSRF)."""
    return await set_kill_switch(
        session,
        active=payload.active,
        reason=payload.reason,
        actor=admin.get("sub", "admin"),
    )


# ---------------------------------------------------------------------------
# Admin Audit Logs
# ---------------------------------------------------------------------------
@router.get("/api/system/audit-logs")
async def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> list[dict[str, Any]]:
    """Retrieve audit log history ordered newest first."""
    logs = await get_recent_audit_logs(session, limit=limit, offset=offset, action=action)
    return [
        {
            "id": log.id,
            "at": log.at,
            "actor": log.actor,
            "action": log.action,
            "entity": log.entity,
            "entity_id": log.entity_id,
            "detail": log.detail,
        }
        for log in logs
    ]


# ---------------------------------------------------------------------------
# Account & Operational Limits
# ---------------------------------------------------------------------------
async def _get_or_create_primary_account(session: AsyncSession) -> Account:
    res = await session.execute(select(Account).limit(1))
    acc = res.scalar_one_or_none()
    if acc:
        return acc

    now = utc_now_iso()
    acc = Account(
        id="acc_default",
        username="affiliate_curator",
        display_name="Affiliate Curator",
        country_code="US",
        timezone="America/New_York",
        active_hours_start=9,
        active_hours_end=21,
        automation_mode="manual_approve",
        sample_review_pct=30,
        warmup_started_at=now,
        status="active",
        created_at=now,
        updated_at=now,
    )
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    return acc


@router.get("/api/system/account", response_model=AccountSettingsResponse)
async def get_account_settings(
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> AccountSettingsResponse:
    """Get operational account settings and hard limits."""
    acc = await _get_or_create_primary_account(session)
    t_status = get_token_status(acc)

    warmup_age_days = 0
    if acc.warmup_started_at:
        try:
            start_dt = datetime.fromisoformat(acc.warmup_started_at.replace("Z", "+00:00"))
            warmup_age_days = max(0, (utc_now() - start_dt).days)
        except Exception:
            pass

    return AccountSettingsResponse(
        id=acc.id,
        username=acc.username,
        threads_user_id=acc.threads_user_id,
        country_code=acc.country_code,
        timezone=acc.timezone,
        active_hours_start=acc.active_hours_start,
        active_hours_end=acc.active_hours_end,
        automation_mode=acc.automation_mode,  # type: ignore[arg-type]
        sample_review_pct=acc.sample_review_pct,
        warmup_started_at=acc.warmup_started_at,
        warmup_age_days=warmup_age_days,
        token_valid=t_status["valid"],
        token_expires_at=t_status["expires_at"],
        days_until_token_expiry=t_status["days_remaining"],
        hard_max_posts_per_day=settings.HARD_MAX_POSTS_PER_DAY,
        hard_max_replies_per_day=settings.HARD_MAX_REPLIES_PER_DAY,
    )


@router.get("/api/system/full-auto-eligibility", response_model=FullAutoEligibilityResponse)
async def check_full_auto_eligibility(
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> FullAutoEligibilityResponse:
    """Evaluate whether the account qualifies for full_auto autonomous mode (docs/06 §6)."""
    acc = await _get_or_create_primary_account(session)
    now = utc_now()

    # 1. Warmup Age >= 14 days
    age_days = 0
    if acc.warmup_started_at:
        try:
            start_dt = datetime.fromisoformat(acc.warmup_started_at.replace("Z", "+00:00"))
            age_days = (now - start_dt).days
        except Exception:
            pass
    age_passed = age_days >= 14

    # 2. Minimum 20 published posts total
    total_posts_res = await session.execute(
        select(func.count(Post.id)).where(Post.account_id == acc.id)
    )
    total_posts = total_posts_res.scalar_one() or 0
    posts_passed = total_posts >= 20

    # 3. 0 safety incidents (warning/critical) in last 14 days
    fourteen_days_ago = (now - timedelta(days=14)).isoformat()
    incidents_res = await session.execute(
        select(func.count(Incident.id)).where(
            Incident.created_at >= fourteen_days_ago,
            Incident.severity.in_(["warning", "critical"]),
        )
    )
    incident_count = incidents_res.scalar_one() or 0
    incidents_passed = incident_count == 0

    # 4. Non-affiliate ratio >= 30%
    non_aff_res = await session.execute(
        select(func.count(Post.id)).where(
            Post.account_id == acc.id,
            Post.is_affiliate.is_(False),
        )
    )
    non_aff_count = non_aff_res.scalar_one() or 0
    ratio = (non_aff_count / total_posts) if total_posts > 0 else 0.0
    ratio_passed = ratio >= 0.30

    # 5. Token valid and Kill Switch OFF
    token_status = get_token_status(acc)
    ks_active = await is_kill_switch_active(session)
    readiness_passed = token_status["valid"] and not ks_active

    eligible = age_passed and posts_passed and incidents_passed and ratio_passed and readiness_passed

    criteria = {
        "min_account_age": FullAutoCriterion(
            required="≥ 14 hari",
            current=f"{age_days} hari",
            passed=age_passed,
            label="Usia akun minimal 14 hari sejak warm-up",
        ),
        "min_published_posts": FullAutoCriterion(
            required="≥ 20 post",
            current=f"{total_posts} post",
            passed=posts_passed,
            label="Minimal 20 postingan telah berhasil terbit",
        ),
        "zero_incidents_14d": FullAutoCriterion(
            required="0 insiden",
            current=f"{incident_count} insiden",
            passed=incidents_passed,
            label="Nol insiden keamanan atau kill switch dalam 14 hari terakhir",
        ),
        "non_affiliate_ratio": FullAutoCriterion(
            required="≥ 30%",
            current=f"{int(ratio * 100)}%",
            passed=ratio_passed,
            label="Rasio konten non-afiliasi kumulatif minimal 30%",
        ),
        "token_and_killswitch_ready": FullAutoCriterion(
            required="Token Aktif & Kill Switch OFF",
            current="Siap" if readiness_passed else "Tidak Siap (Kill Switch ON atau Token Expired)",
            passed=readiness_passed,
            label="Token Threads valid dan Kill Switch tidak aktif",
        ),
    }

    if eligible:
        summary = "Akun memenuhi semua 5 syarat kelayakan untuk mode full_auto (otonom)."
    else:
        unmet = [c.label for c in criteria.values() if not c.passed]
        summary = f"Akun belum memenuhi syarat kelayakan: {'; '.join(unmet)}."

    return FullAutoEligibilityResponse(
        eligible=eligible,
        summary_reason=summary,
        criteria=criteria,
    )


@router.put("/api/system/account", response_model=AccountSettingsResponse)
async def update_account_settings(
    payload: AccountSettingsUpdate,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> AccountSettingsResponse:
    """Update operational limits and automation mode.

    If switching to full_auto, eligibility is strictly verified.
    """
    acc = await _get_or_create_primary_account(session)

    # Validate active hours consistency
    start_h = payload.active_hours_start if payload.active_hours_start is not None else acc.active_hours_start
    end_h = payload.active_hours_end if payload.active_hours_end is not None else acc.active_hours_end
    if start_h >= end_h:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Jam mulai aktif ({start_h}) harus lebih kecil dari jam selesai ({end_h}).",
        )

    # Validate full_auto eligibility if requesting switch
    if payload.automation_mode == "full_auto" and acc.automation_mode != "full_auto":
        elig = await check_full_auto_eligibility(session=session, admin=admin)
        if not elig.eligible:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "Peralihan ke mode full_auto ditolak. Syarat kelayakan belum terpenuhi.",
                    "reason": elig.summary_reason,
                },
            )

    changed_fields: dict[str, Any] = {}
    if payload.active_hours_start is not None:
        changed_fields["active_hours_start"] = payload.active_hours_start
        acc.active_hours_start = payload.active_hours_start
    if payload.active_hours_end is not None:
        changed_fields["active_hours_end"] = payload.active_hours_end
        acc.active_hours_end = payload.active_hours_end
    if payload.automation_mode is not None:
        changed_fields["automation_mode"] = payload.automation_mode
        acc.automation_mode = payload.automation_mode
    if payload.sample_review_pct is not None:
        changed_fields["sample_review_pct"] = payload.sample_review_pct
        acc.sample_review_pct = payload.sample_review_pct
    if payload.timezone is not None:
        changed_fields["timezone"] = payload.timezone
        acc.timezone = payload.timezone

    acc.updated_at = utc_now_iso()
    await session.commit()
    await session.refresh(acc)

    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="update_account_settings",
        entity="accounts",
        entity_id=acc.id,
        detail=changed_fields,
    )

    return await get_account_settings(session=session, admin=admin)


# ---------------------------------------------------------------------------
# Incidents Management
# ---------------------------------------------------------------------------
@router.get("/api/system/incidents", response_model=list[IncidentResponse])
async def list_incidents(
    resolved: bool | None = Query(default=None, description="Filter by resolution state"),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> list[IncidentResponse]:
    """List system incidents ordered newest first."""
    query = select(Incident)
    if resolved is True:
        query = query.where(Incident.resolved_at.is_not(None))
    elif resolved is False:
        query = query.where(Incident.resolved_at.is_(None))

    query = query.order_by(Incident.created_at.desc()).limit(limit)
    res = await session.execute(query)
    incidents = res.scalars().all()
    return [
        IncidentResponse(
            id=inc.id,
            severity=inc.severity,  # type: ignore[arg-type]
            code=inc.code,
            detail=inc.detail,
            resolved_at=inc.resolved_at,
            created_at=inc.created_at,
        )
        for inc in incidents
    ]


@router.post("/api/system/incidents/{incident_id}/resolve", response_model=IncidentResponse)
async def resolve_incident(
    incident_id: str,
    payload: IncidentResolveRequest,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> IncidentResponse:
    """Resolve an incident with mandatory resolution notes and audit logging."""
    res = await session.execute(select(Incident).where(Incident.id == incident_id))
    inc = res.scalar_one_or_none()
    if not inc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Insiden dengan ID {incident_id!r} tidak ditemukan.",
        )

    now = utc_now_iso()
    inc.resolved_at = now

    existing_detail = {}
    if inc.detail:
        try:
            existing_detail = json.loads(inc.detail) if inc.detail.startswith("{") else {"raw": inc.detail}
        except Exception:
            existing_detail = {"raw": inc.detail}

    existing_detail["resolution"] = {
        "notes": payload.resolution_notes,
        "resolved_by": admin.get("sub", "admin"),
        "resolved_at": now,
    }
    inc.detail = json.dumps(existing_detail)
    await session.commit()
    await session.refresh(inc)

    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="resolve_incident",
        entity="incidents",
        entity_id=inc.id,
        detail={"code": inc.code, "resolution_notes": payload.resolution_notes},
    )

    return IncidentResponse(
        id=inc.id,
        severity=inc.severity,  # type: ignore[arg-type]
        code=inc.code,
        detail=inc.detail,
        resolved_at=inc.resolved_at,
        created_at=inc.created_at,
    )
