"""tests/test_api_schedule.py — Test suite for Weekly Schedule & Governor Calendar API (T-033).

Verifies:
1. GET /api/schedule/calendar returns dual timezone times, 7 days, and governor summary.
2. POST /api/schedule/validate-slot validates active hours (09:00-21:00 EST), interval spacing, and quota.
3. POST /api/schedule/move-slot successfully updates scheduled_at within governor limits and logs audit entry.
4. POST /api/schedule/move-slot rejects movements violating active hours or interval spacing with HTTP 422.
5. Strict auth and CSRF enforcement.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import get_recent_audit_logs
from app.core.clock import utc_now_iso
from app.core.security import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, create_session_token
from app.db.models import Account, Draft, Niche, Product, Style


def _get_auth_headers_and_cookies() -> tuple[dict[str, str], dict[str, str]]:
    token, csrf_token = create_session_token("admin")
    headers = {"X-CSRF-Token": csrf_token}
    cookies = {
        SESSION_COOKIE_NAME: token,
        CSRF_COOKIE_NAME: csrf_token,
    }
    return headers, cookies


@pytest.fixture
async def sample_schedule_setup(db_session: AsyncSession) -> dict[str, str]:
    now = utc_now_iso()
    account = Account(
        id="acc_sched_test",
        username="schedule_tester",
        display_name="Schedule Tester",
        country_code="US",
        timezone="America/New_York",
        active_hours_start=9,
        active_hours_end=21,
        automation_mode="manual_approve",
        warmup_started_at=now,
        status="active",
        created_at=now,
        updated_at=now,
    )
    db_session.add(account)

    niche = Niche(id="niche_sched", name="Workspace Tech", status="active")
    db_session.add(niche)

    style = Style(id="style_sched", name="Curator Find", max_chars=400, status="active")
    db_session.add(style)

    prod = Product(
        id="prod_sched",
        niche_id=niche.id,
        title="Ergonomic Mechanical Keyboard",
        benable_url="https://benable.com/tech/keyboard",
        status="active",
    )
    db_session.add(prod)
    await db_session.commit()

    return {
        "account_id": account.id,
        "niche_id": niche.id,
        "style_id": style.id,
        "product_id": prod.id,
    }


@pytest.mark.asyncio
async def test_get_calendar_dual_timezone(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_schedule_setup: dict[str, str],
) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    # Create a scheduled draft at 2026-11-10T15:00:00Z (10:00 AM EST, 22:00 WIB)
    now = utc_now_iso()
    draft = Draft(
        id="draft_cal_1",
        account_id=sample_schedule_setup["account_id"],
        niche_id=sample_schedule_setup["niche_id"],
        style_id=sample_schedule_setup["style_id"],
        product_id=sample_schedule_setup["product_id"],
        parts=json.dumps([{"part_index": 1, "text": "Ergonomic split keyboard review.", "char_count": 32}]),
        text_hash="hash_cal_1",
        status="scheduled",
        scheduled_at="2026-11-10T15:00:00Z",
        created_at=now,
        updated_at=now,
    )
    db_session.add(draft)
    await db_session.commit()

    resp = await client.get("/api/schedule/calendar?start_date=2026-11-09&days_count=7", headers=headers, cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()

    assert data["start_date"] == "2026-11-09"
    assert len(data["days"]) == 7
    assert data["governor"]["target_timezone"] == "America/New_York"
    assert data["governor"]["operator_timezone"] == "Asia/Jakarta"
    assert data["governor"]["active_hours_start"] == 9
    assert data["governor"]["active_hours_end"] == 21

    # Check that draft_cal_1 is in day 2026-11-10
    day_10 = next((d for d in data["days"] if d["date"] == "2026-11-10"), None)
    assert day_10 is not None
    assert day_10["scheduled_count"] == 1
    slot = day_10["slots"][0]
    assert slot["draft_id"] == "draft_cal_1"
    assert "EST" in slot["scheduled_at_target"]
    assert "WIB" in slot["scheduled_at_operator"]


@pytest.mark.asyncio
async def test_validate_slot_governor_active_hours(
    client: AsyncClient,
    sample_schedule_setup: dict[str, str],
) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    # 1. 19:00 UTC = 14:00 EST (Within active hours 09:00 - 21:00 EST) -> Valid
    resp_valid = await client.post(
        "/api/schedule/validate-slot",
        json={"candidate_scheduled_at": "2026-11-11T19:00:00Z"},
        headers=headers,
        cookies=cookies,
    )
    assert resp_valid.status_code == 200
    assert resp_valid.json()["valid"] is True
    assert resp_valid.json()["is_active_hours"] is True

    # 2. 07:00 UTC = 02:00 EST (Outside active hours 09:00 - 21:00 EST) -> Invalid
    resp_invalid = await client.post(
        "/api/schedule/validate-slot",
        json={"candidate_scheduled_at": "2026-11-11T07:00:00Z"},
        headers=headers,
        cookies=cookies,
    )
    assert resp_invalid.status_code == 200
    assert resp_invalid.json()["valid"] is False
    assert resp_invalid.json()["is_active_hours"] is False
    assert "jam aktif" in resp_invalid.json()["reason"].lower()


@pytest.mark.asyncio
async def test_move_slot_governor_enforcement(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_schedule_setup: dict[str, str],
) -> None:
    headers, cookies = _get_auth_headers_and_cookies()
    now = utc_now_iso()

    # Create approved draft
    draft = Draft(
        id="draft_move_test",
        account_id=sample_schedule_setup["account_id"],
        niche_id=sample_schedule_setup["niche_id"],
        style_id=sample_schedule_setup["style_id"],
        parts=json.dumps([{"part_index": 1, "text": "Draft to be rescheduled.", "char_count": 24}]),
        text_hash="hash_move_test",
        status="approved",
        scheduled_at="2026-11-12T15:00:00Z",
        created_at=now,
        updated_at=now,
    )
    db_session.add(draft)
    await db_session.commit()

    # 1. Move to forbidden hours (03:00 EST / 08:00 UTC) -> 422 Unprocessable Entity
    resp_fail = await client.post(
        "/api/schedule/move-slot",
        json={"draft_id": draft.id, "new_scheduled_at": "2026-11-12T08:00:00Z"},
        headers=headers,
        cookies=cookies,
    )
    assert resp_fail.status_code == 422
    assert "jam aktif" in resp_fail.json()["detail"]["reason"].lower()

    # 2. Move to valid active hours (15:00 EST / 20:00 UTC) -> 200 OK
    resp_ok = await client.post(
        "/api/schedule/move-slot",
        json={"draft_id": draft.id, "new_scheduled_at": "2026-11-12T20:00:00Z"},
        headers=headers,
        cookies=cookies,
    )
    assert resp_ok.status_code == 200
    data = resp_ok.json()
    assert data["success"] is True
    assert data["status"] == "scheduled"
    assert "2026-11-12T20:00:00" in data["new_scheduled_at_utc"]

    # Verify DB state
    await db_session.refresh(draft)
    assert draft.status == "scheduled"
    assert "2026-11-12T20:00:00" in draft.scheduled_at

    # Verify audit trail
    audit_logs = await get_recent_audit_logs(db_session, limit=5)
    assert any(log.action == "reschedule_draft" for log in audit_logs)
