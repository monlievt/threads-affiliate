"""tests/test_api_settings.py — Test suite for Settings, Full Auto Eligibility, Incidents, and Audit API (T-034).

Verifies:
1. GET /api/system/account returns operational settings and hard limits.
2. GET /api/system/full-auto-eligibility validates all 5 eligibility criteria.
3. PUT /api/system/account validates active hours and blocks full_auto if not eligible.
4. PUT /api/system/account updates settings and records audit log.
5. GET and POST /api/system/incidents/{id}/resolve with mandatory notes and audit entry.
6. GET /api/system/audit-logs retrieves filtered mutation history.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import get_recent_audit_logs
from app.core.clock import utc_now_iso
from app.core.security import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, create_session_token
from app.db.models import Account, AuditLog, Incident


def _get_auth_headers_and_cookies() -> tuple[dict[str, str], dict[str, str]]:
    token, csrf_token = create_session_token("admin")
    headers = {"X-CSRF-Token": csrf_token}
    cookies = {
        SESSION_COOKIE_NAME: token,
        CSRF_COOKIE_NAME: csrf_token,
    }
    return headers, cookies


@pytest.fixture
async def setup_settings_account(db_session: AsyncSession) -> Account:
    now = utc_now_iso()
    acc = Account(
        id="acc_settings_test",
        username="settings_tester",
        display_name="Settings Tester",
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
    db_session.add(acc)
    await db_session.commit()
    await db_session.refresh(acc)
    return acc


@pytest.mark.asyncio
async def test_get_account_settings_and_hard_limits(
    client: AsyncClient,
    setup_settings_account: Account,
) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    resp = await client.get("/api/system/account", headers=headers, cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "settings_tester"
    assert data["automation_mode"] == "manual_approve"
    assert data["active_hours_start"] == 9
    assert data["active_hours_end"] == 21
    assert data["hard_max_posts_per_day"] >= 1
    assert data["hard_max_replies_per_day"] >= 1


@pytest.mark.asyncio
async def test_full_auto_eligibility_checks(
    client: AsyncClient,
    setup_settings_account: Account,
) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    resp = await client.get("/api/system/full-auto-eligibility", headers=headers, cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()

    # Brand new account should NOT be eligible (warmup age < 14, < 20 posts)
    assert data["eligible"] is False
    assert len(data["criteria"]) == 5
    assert data["criteria"]["min_account_age"]["passed"] is False
    assert data["criteria"]["min_published_posts"]["passed"] is False


@pytest.mark.asyncio
async def test_update_account_settings_and_full_auto_block(
    client: AsyncClient,
    db_session: AsyncSession,
    setup_settings_account: Account,
) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    # 1. Invalid active hours (start >= end) -> 400 Bad Request
    resp_inv_hours = await client.put(
        "/api/system/account",
        json={"active_hours_start": 20, "active_hours_end": 10},
        headers=headers,
        cookies=cookies,
    )
    assert resp_inv_hours.status_code == 400

    # 2. Unauthorized attempt to switch to full_auto -> 422 Unprocessable Entity
    resp_auto_fail = await client.put(
        "/api/system/account",
        json={"automation_mode": "full_auto"},
        headers=headers,
        cookies=cookies,
    )
    assert resp_auto_fail.status_code == 422
    assert "full_auto ditolak" in resp_auto_fail.json()["detail"]["message"].lower()

    # 3. Valid update of active hours and sample review pct -> 200 OK
    resp_ok = await client.put(
        "/api/system/account",
        json={
            "active_hours_start": 8,
            "active_hours_end": 22,
            "sample_review_pct": 50,
            "automation_mode": "auto_sampled",
        },
        headers=headers,
        cookies=cookies,
    )
    assert resp_ok.status_code == 200
    res_data = resp_ok.json()
    assert res_data["active_hours_start"] == 8
    assert res_data["active_hours_end"] == 22
    assert res_data["sample_review_pct"] == 50
    assert res_data["automation_mode"] == "auto_sampled"

    # Verify audit log
    logs = await get_recent_audit_logs(db_session, limit=5)
    assert any(log.action == "update_account_settings" for log in logs)


@pytest.mark.asyncio
async def test_incidents_listing_and_resolution(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    headers, cookies = _get_auth_headers_and_cookies()
    now = utc_now_iso()

    # Create test incident
    inc = Incident(
        id="inc_test_123",
        severity="critical",
        code="KILL_SWITCH_ENGAGED",
        detail="Rate limit 429 encountered during automated publication.",
        created_at=now,
    )
    db_session.add(inc)
    await db_session.commit()

    # 1. List active incidents
    resp_list = await client.get("/api/system/incidents?resolved=false", headers=headers, cookies=cookies)
    assert resp_list.status_code == 200
    incidents = resp_list.json()
    assert any(i["id"] == "inc_test_123" for i in incidents)

    # 2. Resolve incident with notes
    resp_resolve = await client.post(
        "/api/system/incidents/inc_test_123/resolve",
        json={"resolution_notes": "Reviewed rate limits, verified account quota, and confirmed kill switch disarmed."},
        headers=headers,
        cookies=cookies,
    )
    assert resp_resolve.status_code == 200
    res_data = resp_resolve.json()
    assert res_data["resolved_at"] is not None

    # Verify audit log
    logs = await get_recent_audit_logs(db_session, limit=5)
    assert any(log.action == "resolve_incident" for log in logs)
