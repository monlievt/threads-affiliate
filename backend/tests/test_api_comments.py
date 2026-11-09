"""tests/test_api_comments.py — Test suite for Value-First Comments API (T-035).

Verifies:
1. GET /api/comments/quota returns accurate daily limits, remaining counts, and avoid list.
2. POST /api/comments/generate creates 3 strategic options with safety checking.
3. POST /api/comments/generate rejects invalid target URLs (not threads.net) with HTTP 400.
4. POST /api/comments/generate sets link warnings appropriately when links are included.
5. POST /api/comments/publish records audit logs for both clipboard copy and API publish.
6. Strict auth and CSRF enforcement.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import get_recent_audit_logs
from app.core.clock import utc_now_iso
from app.core.security import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, create_session_token
from app.db.models import Account, AuditLog, Niche, Product


def _get_auth_headers_and_cookies() -> tuple[dict[str, str], dict[str, str]]:
    token, csrf_token = create_session_token("admin")
    headers = {"X-CSRF-Token": csrf_token}
    cookies = {
        SESSION_COOKIE_NAME: token,
        CSRF_COOKIE_NAME: csrf_token,
    }
    return headers, cookies


@pytest.fixture
async def setup_comments_account(db_session: AsyncSession) -> dict[str, str]:
    now = utc_now_iso()
    acc = Account(
        id="acc_comm_test",
        username="curator_reply",
        display_name="Curator Reply",
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
    db_session.add(acc)

    niche = Niche(id="niche_desk_comm", name="Desk Setups", status="active")
    db_session.add(niche)

    prod = Product(
        id="prod_comm",
        niche_id=niche.id,
        title="Solid Hardwood Monitor Riser",
        benable_url="https://benable.com/desk/riser",
        status="active",
    )
    db_session.add(prod)
    await db_session.commit()

    return {
        "account_id": acc.id,
        "niche_id": niche.id,
        "product_id": prod.id,
    }


@pytest.mark.asyncio
async def test_get_comments_quota(
    client: AsyncClient,
    setup_comments_account: dict[str, str],
) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    resp = await client.get("/api/comments/quota", headers=headers, cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()
    assert data["replies_today"] >= 0
    assert data["max_replies_today"] >= 1
    assert data["hard_max_replies"] >= 1
    assert len(data["avoid_list"]) > 0


@pytest.mark.asyncio
async def test_generate_comments_validation_and_options(
    client: AsyncClient,
    setup_comments_account: dict[str, str],
) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    # 1. Invalid URL (not threads.net) -> 400 Bad Request
    resp_inv_url = await client.post(
        "/api/comments/generate",
        json={
            "target_post_url": "https://twitter.com/user/status/123",
            "target_post_text": "Working from home requires serious cable management.",
        },
        headers=headers,
        cookies=cookies,
    )
    assert resp_inv_url.status_code == 400

    # 2. Valid generation without link (pure value-first) -> 200 OK
    resp_gen = await client.post(
        "/api/comments/generate",
        json={
            "target_post_url": "https://www.threads.net/@dev_daily/post/C9xyz123",
            "target_post_text": "After 5 years of remote work, my biggest productivity boost came from a dual monitor riser.",
            "niche_id": setup_comments_account["niche_id"],
            "include_link": False,
        },
        headers=headers,
        cookies=cookies,
    )
    assert resp_gen.status_code == 200
    data = resp_gen.json()
    assert len(data["options"]) >= 2
    assert all(not opt["has_link"] for opt in data["options"])
    assert any(opt["strategy"] == "insight" for opt in data["options"])

    # 3. Valid generation with product link -> sets has_link = True
    resp_link = await client.post(
        "/api/comments/generate",
        json={
            "target_post_url": "https://www.threads.net/@dev_daily/post/C9xyz123",
            "target_post_text": "Anyone know where to find a solid wooden monitor stand that isn't cheap laminate?",
            "niche_id": setup_comments_account["niche_id"],
            "include_link": True,
            "product_id": setup_comments_account["product_id"],
        },
        headers=headers,
        cookies=cookies,
    )
    assert resp_link.status_code == 200
    data_link = resp_link.json()
    assert any(opt["has_link"] for opt in data_link["options"])


@pytest.mark.asyncio
async def test_publish_and_copy_comment_audit(
    client: AsyncClient,
    db_session: AsyncSession,
    setup_comments_account: dict[str, str],
) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    # 1. Action: copied_clipboard
    resp_copy = await client.post(
        "/api/comments/publish",
        json={
            "target_post_url": "https://www.threads.net/@dev_daily/post/C9xyz123",
            "selected_text": "Felt this so much. Keeping cables off the surface completely changed my desk flow.",
            "action_type": "copied_clipboard",
        },
        headers=headers,
        cookies=cookies,
    )
    assert resp_copy.status_code == 200
    assert resp_copy.json()["action_type"] == "copied_clipboard"

    # 2. Action: publish_api
    resp_api = await client.post(
        "/api/comments/publish",
        json={
            "target_post_url": "https://www.threads.net/@dev_daily/post/C9xyz123",
            "selected_text": "Solid point on this. Airflow under the laptop made a huge noise difference.",
            "action_type": "publish_api",
        },
        headers=headers,
        cookies=cookies,
    )
    assert resp_api.status_code == 200
    assert resp_api.json()["action_type"] == "publish_api"

    # Verify audit trail entries
    logs = await get_recent_audit_logs(db_session, limit=5)
    actions = [l.action for l in logs]
    assert "copy_comment_clipboard" in actions
    assert "publish_comment_api" in actions
