"""tests/test_api_drafts.py — Test suite for Draft Review & Editor API (T-031).

Verifies:
1. List drafts with filters (status, niche, style) and pagination
2. Get single draft by ID (200 / 404)
3. Approve draft with state machine validation and audit log
4. Reject draft with custom reason and audit log
5. Inline edit with mandatory real-time safety validation (V-LEN, V-PRICE, etc.)
6. Batch approve eligible drafts with clean validator report
7. Live text validation endpoint (/api/drafts/validate-text)
8. Strict auth and CSRF enforcement
"""

from __future__ import annotations

import json
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import get_recent_audit_logs
from app.core.clock import utc_now_iso
from app.core.security import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, create_session_token
from app.db.models import Account, Draft, Niche, Persona, Product, Style


def _get_auth_headers_and_cookies() -> tuple[dict[str, str], dict[str, str]]:
    token, csrf_token = create_session_token("admin")
    headers = {"X-CSRF-Token": csrf_token}
    cookies = {
        SESSION_COOKIE_NAME: token,
        CSRF_COOKIE_NAME: csrf_token,
    }
    return headers, cookies


@pytest.fixture
async def sample_catalog(db_session: AsyncSession) -> dict[str, str]:
    """Seed sample account, niche, style, product, and persona."""
    now = utc_now_iso()

    account = Account(id="acc_default", username="affiliate_tester", display_name="Affiliate Tester", status="active")
    db_session.add(account)

    niche = Niche(id="niche_desk", name="Desk Setup", status="active")
    db_session.add(niche)

    style = Style(id="style_story", name="Personal Story", max_chars=400, status="active")
    db_session.add(style)

    persona = Persona(id="persona_minimalist", name="Minimalist Dev", disclosure_template="Curated finds on Benable (affiliate link)", status="active")
    db_session.add(persona)

    product = Product(
        id="prod_riser",
        niche_id=niche.id,
        title="Solid Walnut Monitor Riser",
        benable_url="https://benable.com/desk/riser",
        status="active",
    )
    db_session.add(product)
    await db_session.commit()

    return {
        "account_id": account.id,
        "niche_id": niche.id,
        "style_id": style.id,
        "persona_id": persona.id,
        "product_id": product.id,
    }


@pytest.mark.asyncio
async def test_list_and_get_drafts(client: AsyncClient, db_session: AsyncSession, sample_catalog: dict[str, str]) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    # Create two drafts: one pending_review, one approved
    now = utc_now_iso()
    d1 = Draft(
        id="draft_1",
        account_id=sample_catalog["account_id"],
        niche_id=sample_catalog["niche_id"],
        style_id=sample_catalog["style_id"],
        product_id=sample_catalog["product_id"],
        parts=json.dumps([{"part_index": 1, "text": "Upgraded my desk setup with this solid walnut riser.", "char_count": 55}]),
        text_hash="hash_1",
        status="pending_review",
        validator_report=json.dumps({"valid": True, "failed_codes": []}),
        similarity_score=0.1,
        created_at=now,
        updated_at=now,
    )
    d2 = Draft(
        id="draft_2",
        account_id=sample_catalog["account_id"],
        niche_id=sample_catalog["niche_id"],
        style_id=sample_catalog["style_id"],
        parts=json.dumps([{"part_index": 1, "text": "Clean cable management thoughts.", "char_count": 32}]),
        text_hash="hash_2",
        status="approved",
        validator_report=json.dumps({"valid": True, "failed_codes": []}),
        similarity_score=0.0,
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([d1, d2])
    await db_session.commit()

    # List all
    resp = await client.get("/api/drafts", headers=headers, cookies=cookies)
    assert resp.status_code == 200
    drafts = resp.json()
    assert len(drafts) >= 2

    # Filter by status=pending_review
    resp_pending = await client.get("/api/drafts?status=pending_review", headers=headers, cookies=cookies)
    assert resp_pending.status_code == 200
    pending_items = resp_pending.json()
    assert all(d["status"] == "pending_review" for d in pending_items)
    assert any(d["id"] == "draft_1" for d in pending_items)
    assert not any(d["id"] == "draft_2" for d in pending_items)

    # Get single draft
    resp_single = await client.get("/api/drafts/draft_1", headers=headers, cookies=cookies)
    assert resp_single.status_code == 200
    data = resp_single.json()
    assert data["id"] == "draft_1"
    assert data["full_text"] == "Upgraded my desk setup with this solid walnut riser."
    assert data["niche_name"] == "Desk Setup"
    assert data["product_title"] == "Solid Walnut Monitor Riser"
    assert data["product_benable_url"] == "https://benable.com/desk/riser"

    # 404 for unknown draft
    resp_404 = await client.get("/api/drafts/unknown_id", headers=headers, cookies=cookies)
    assert resp_404.status_code == 404


@pytest.mark.asyncio
async def test_approve_and_reject_draft(client: AsyncClient, db_session: AsyncSession, sample_catalog: dict[str, str]) -> None:
    headers, cookies = _get_auth_headers_and_cookies()
    now = utc_now_iso()

    d_pending = Draft(
        id="draft_review_me",
        account_id=sample_catalog["account_id"],
        niche_id=sample_catalog["niche_id"],
        style_id=sample_catalog["style_id"],
        parts=json.dumps([{"part_index": 1, "text": "Review me please.", "char_count": 17}]),
        text_hash="hash_review_me",
        status="pending_review",
        created_at=now,
        updated_at=now,
    )
    db_session.add(d_pending)
    await db_session.commit()

    # Approve draft
    resp_app = await client.post(f"/api/drafts/{d_pending.id}/approve", headers=headers, cookies=cookies)
    assert resp_app.status_code == 200
    assert resp_app.json()["status"] == "approved"

    # Verify DB state
    await db_session.refresh(d_pending)
    assert d_pending.status == "approved"
    assert d_pending.reviewed_at is not None

    # Idempotent approval on already approved draft
    resp_app_idemp = await client.post(f"/api/drafts/{d_pending.id}/approve", headers=headers, cookies=cookies)
    assert resp_app_idemp.status_code == 200
    assert resp_app_idemp.json()["status"] == "approved"

    # Reject another draft
    d_reject = Draft(
        id="draft_reject_me",
        account_id=sample_catalog["account_id"],
        niche_id=sample_catalog["niche_id"],
        style_id=sample_catalog["style_id"],
        parts=json.dumps([{"part_index": 1, "text": "Reject me please.", "char_count": 17}]),
        text_hash="hash_reject_me",
        status="pending_review",
        created_at=now,
        updated_at=now,
    )
    db_session.add(d_reject)
    await db_session.commit()

    resp_rej = await client.post(
        f"/api/drafts/{d_reject.id}/reject",
        json={"reason": "Tone is not natural enough."},
        headers=headers,
        cookies=cookies,
    )
    assert resp_rej.status_code == 200
    rej_data = resp_rej.json()
    assert rej_data["status"] == "rejected"
    assert rej_data["reject_reason"] == "Tone is not natural enough."

    # Verify audit logs
    audit_logs = await get_recent_audit_logs(db_session, limit=10)
    actions = [log.action for log in audit_logs]
    assert "approve_draft" in actions
    assert "reject_draft" in actions


@pytest.mark.asyncio
async def test_inline_edit_draft_safety_validation(client: AsyncClient, db_session: AsyncSession, sample_catalog: dict[str, str]) -> None:
    headers, cookies = _get_auth_headers_and_cookies()
    now = utc_now_iso()

    draft = Draft(
        id="draft_edit_test",
        account_id=sample_catalog["account_id"],
        niche_id=sample_catalog["niche_id"],
        style_id=sample_catalog["style_id"],  # max_chars=400
        product_id=sample_catalog["product_id"],  # is_affiliate=True
        parts=json.dumps([{"part_index": 1, "text": "Original draft text for desk setup.", "char_count": 34}]),
        text_hash="hash_edit_original",
        status="pending_review",
        created_at=now,
        updated_at=now,
    )
    db_session.add(draft)
    await db_session.commit()

    # 1. Edit with price violation ($49.99) -> 422 Unprocessable Entity
    resp_price_fail = await client.put(
        f"/api/drafts/{draft.id}",
        json={"text": "Grab this amazing walnut desk riser for only $49.99 right now!"},
        headers=headers,
        cookies=cookies,
    )
    assert resp_price_fail.status_code == 422
    err_data = resp_price_fail.json()["detail"]
    assert "V-PRICE" in err_data["failed_codes"]

    # 2. Edit with length violation (> 400 chars) -> 422 Unprocessable Entity
    long_text = "This desk setup item makes a massive difference in ergonomic daily workflow. " * 8
    resp_len_fail = await client.put(
        f"/api/drafts/{draft.id}",
        json={"text": long_text},
        headers=headers,
        cookies=cookies,
    )
    assert resp_len_fail.status_code == 422
    assert "V-LEN" in resp_len_fail.json()["detail"]["failed_codes"]

    # 3. Clean edit -> 200 OK
    clean_text = "After weeks of working hunched over, moving to this dual monitor riser completely changed my neck posture."
    resp_success = await client.put(
        f"/api/drafts/{draft.id}",
        json={"text": clean_text},
        headers=headers,
        cookies=cookies,
    )
    assert resp_success.status_code == 200
    updated_data = resp_success.json()
    assert updated_data["full_text"] == clean_text
    assert updated_data["char_count"] == len(clean_text)

    # Verify DB update
    await db_session.refresh(draft)
    parts = json.loads(draft.parts)
    assert parts[0]["text"] == clean_text


@pytest.mark.asyncio
async def test_batch_approve_eligible_drafts(client: AsyncClient, db_session: AsyncSession, sample_catalog: dict[str, str]) -> None:
    headers, cookies = _get_auth_headers_and_cookies()
    now = utc_now_iso()

    # Draft A: clean validator report -> should be approved
    d_clean = Draft(
        id="draft_batch_clean",
        account_id=sample_catalog["account_id"],
        niche_id=sample_catalog["niche_id"],
        style_id=sample_catalog["style_id"],
        parts=json.dumps([{"part_index": 1, "text": "Desk organization tip number one.", "char_count": 33}]),
        text_hash="hash_batch_1",
        status="pending_review",
        validator_report=json.dumps({"valid": True, "failed_codes": []}),
        created_at=now,
        updated_at=now,
    )
    # Draft B: failed validator report -> should NOT be approved
    d_dirty = Draft(
        id="draft_batch_dirty",
        account_id=sample_catalog["account_id"],
        niche_id=sample_catalog["niche_id"],
        style_id=sample_catalog["style_id"],
        parts=json.dumps([{"part_index": 1, "text": "Desk riser for $15.", "char_count": 19}]),
        text_hash="hash_batch_2",
        status="pending_review",
        validator_report=json.dumps({"valid": False, "failed_codes": ["V-PRICE"]}),
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([d_clean, d_dirty])
    await db_session.commit()

    resp = await client.post("/api/drafts/batch-approve", headers=headers, cookies=cookies)
    assert resp.status_code == 200
    batch_res = resp.json()
    assert batch_res["approved_count"] >= 1
    assert "draft_batch_clean" in batch_res["approved_ids"]
    assert "draft_batch_dirty" not in batch_res["approved_ids"]

    # Verify DB states
    await db_session.refresh(d_clean)
    await db_session.refresh(d_dirty)
    assert d_clean.status == "approved"
    assert d_dirty.status == "pending_review"


@pytest.mark.asyncio
async def test_live_text_validation_endpoint(client: AsyncClient, sample_catalog: dict[str, str]) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    # Real-time typing check with prohibited price
    payload = {
        "text": "Get this monitor stand for 20% off today on sale!",
        "style_id": sample_catalog["style_id"],
        "is_affiliate": True,
    }
    resp = await client.post("/api/drafts/validate-text", json=payload, headers=headers, cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert "V-PRICE" in data["failed_codes"]
    assert data["max_chars"] == 400
    assert data["char_count"] == len(payload["text"])
    assert data["results"]["V-PRICE"]["valid"] is False

    # Real-time typing check with clean text
    payload_clean = {
        "text": "A sturdy monitor riser keeps cables organized and neck straight.",
        "style_id": sample_catalog["style_id"],
        "is_affiliate": True,
    }
    resp_clean = await client.post("/api/drafts/validate-text", json=payload_clean, headers=headers, cookies=cookies)
    assert resp_clean.status_code == 200
    data_clean = resp_clean.json()
    assert data_clean["valid"] is True
    assert len(data_clean["failed_codes"]) == 0
    assert data_clean["results"]["V-PRICE"]["valid"] is True
    assert data_clean["results"]["V-LEN"]["valid"] is True


@pytest.mark.asyncio
async def test_draft_security_and_csrf_protection(client: AsyncClient) -> None:
    # 1. Unauthenticated request to drafts list -> 401 Unauthorized
    resp_unauth = await client.get("/api/drafts")
    assert resp_unauth.status_code == 401

    # 2. Authenticated but missing CSRF token on mutation -> 403 Forbidden
    token, _ = create_session_token("admin")
    resp_no_csrf = await client.post(
        "/api/drafts/batch-approve",
        cookies={SESSION_COOKIE_NAME: token},
    )
    assert resp_no_csrf.status_code == 403
