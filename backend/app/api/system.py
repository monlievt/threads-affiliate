"""app/api/system.py — System health endpoint.

GET /health returns:
  {
    "status": "ok" | "degraded" | "down",
    "db": "ok" | "error",
    "worker_heartbeat_age_sec": null,
    "token_valid": null,
    "kill_switch": "on" | "off",
    "quota_today": null
  }

HTTP 200 for ok/degraded, HTTP 503 for down.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings
from app.db.session import check_db_connection

router = APIRouter(tags=["system"])


@router.get("/health")
async def health_check() -> JSONResponse:
    """Return system health status.

    - DB reachability is checked via a simple SELECT 1.
    - Kill switch state is read from KILL_SWITCH_ON_START env at startup
      (system_state table is introduced in T-002).
    - worker_heartbeat_age_sec, token_valid, quota_today are null until T-002/T-003.
    """
    db_ok = await check_db_connection()
    db_status = "ok" if db_ok else "error"

    kill_switch_status = "on" if settings.KILL_SWITCH_ON_START else "off"

    if db_ok:
        overall = "ok"
        http_status = 200
    else:
        overall = "down"
        http_status = 503

    payload = {
        "status": overall,
        "db": db_status,
        "worker_heartbeat_age_sec": None,
        "token_valid": None,
        "kill_switch": kill_switch_status,
        "quota_today": None,
    }

    return JSONResponse(content=payload, status_code=http_status)
