"""app/api/system.py — System health, kill switch, and audit endpoints.

Endpoints:
- GET /health: Public liveness and status check
- GET /api/system/kill-switch: Current kill switch status (authenticated admin)
- POST /api/system/kill-switch: Toggle kill switch state (authenticated admin + CSRF)
- GET /api/system/audit-logs: Retrieve recent audit logs (authenticated admin)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.audit import get_recent_audit_logs
from app.core.security import get_current_admin, require_csrf
from app.db.session import AsyncSessionLocal, check_db_connection, get_db
from app.safety.killswitch import (
    get_kill_switch_status,
    is_kill_switch_active,
    set_kill_switch,
)
from app.scheduler.heartbeat import get_worker_heartbeat_info

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

    if db_ok:
        try:
            async with AsyncSessionLocal() as session:
                active = await is_kill_switch_active(session)
                kill_switch_status = "on" if active else "off"
                hb_info = await get_worker_heartbeat_info(session)
                hb_age_sec = hb_info.get("age_seconds")
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
        "token_valid": None,
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
