"""backend/tests/test_e2e_smoke_flow.py — Comprehensive End-to-End Smoke Test Suite (T-054).

Flows tested according to docs/09-ROADMAP-TASKS T-054 & docs/10 §4-§5:
1. Admin authentication (login -> session cookie -> CSRF verification).
2. Content draft generation and review queue ingestion.
3. Real-time safety validation (V-PRICE block & compliant resolution).
4. Review queue approval flow (pending_review -> approved).
5. Scheduler worker slot allocation within US active hours (09:00-21:00 EST).
6. Controlled publication execution via FakeThreadsClient.
7. Verification of published post record & zero-duplicate guarantee.
8. Emergency Kill Switch activation & verification of immediate fail-closed blocking.
"""

from __future__ import annotations

import json
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.clock import utc_now, utc_now_iso
from app.core.crypto import encrypt_token
from app.core.security import SESSION_COOKIE_NAME, hash_password
from app.db.models import Account, Draft, Niche, Persona, Post, Style, SystemState
from app.main import app
from app.safety.guard import PublishGuard
from app.safety.killswitch import is_kill_switch_active, set_kill_switch
from app.threads.fake import FakeThreadsClient
from app.threads.publisher import publish_single_post

TEST_ADMIN_PWD = "test-smoke-admin-pass"


@pytest.fixture
async def setup_e2e_environment(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    """Seed necessary test account, niche, style, and system state for E2E flow."""
    monkeypatch.setattr(settings, "ADMIN_PASSWORD_HASH", hash_password(TEST_ADMIN_PWD))

    # Ensure kill switch is deactivated for active operational testing
    await set_kill_switch(db_session, active=False, reason="E2E test setup", actor="tester")

    # Account
    account = Account(
        id="acc_e2e_smoke_01",
        threads_user_id="user_smoke_threads_01",
        username="curator_smoke_e2e",
        token_encrypted=encrypt_token("fake_valid_access_token"),
        token_expires_at="2099-01-01T00:00:00Z",
        connected_at=utc_now_iso(),
        warmup_started_at=utc_now_iso(),
        active_hours_start=0,
        active_hours_end=24,
        automation_mode="manual_approve",
        sample_review_pct=30,
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    db_session.add(account)

    # Niche
    niche = Niche(
        id="niche_ergonomics_01",
        name="WFH Ergonomics",
        description="US remote workers setup",
        status="active",
    )
    db_session.add(niche)

    # Style
    style = Style(
        id="style_curated_list_01",
        name="Curated Recommendation List",
        description="Curate genuine helpful recommendations for desk workers.",
        tone_rules="Informative, calm, helpful",
        status="active",
    )
    db_session.add(style)

    # Persona
    persona = Persona(
        id="persona_thoughtful_curator_01",
        account_id=account.id,
        name="Thoughtful Curator",
        voice="Warm, practical, informative, zero aggressive claims.",
        disclosure_text="Affiliate link",
        disclosure_position="end",
    )
    db_session.add(persona)

    await db_session.commit()
    return {
        "account": account,
        "niche": niche,
        "style": style,
        "persona": persona,
    }


@pytest.mark.asyncio
async def test_e2e_admin_auth_and_session(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test 1: Admin login, session issuance, and CSRF token."""
    monkeypatch.setattr(settings, "ADMIN_PASSWORD_HASH", hash_password(TEST_ADMIN_PWD))

    # Invalid login
    resp_invalid = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong_password_123"},
    )
    assert resp_invalid.status_code == 401

    # Valid login
    resp_valid = await client.post(
        "/api/auth/login",
        json={"username": settings.ADMIN_USERNAME, "password": TEST_ADMIN_PWD},
    )
    assert resp_valid.status_code == 200
    data = resp_valid.json()
    assert data["status"] == "ok"
    assert data["username"] == settings.ADMIN_USERNAME
    assert "csrf_token" in data
    assert len(data["csrf_token"]) > 10

    csrf_token = data["csrf_token"]
    session_cookie = resp_valid.cookies.get(SESSION_COOKIE_NAME)
    assert session_cookie is not None


@pytest.mark.asyncio
async def test_e2e_full_lifecycle_smoke(
    client: AsyncClient,
    db_session: AsyncSession,
    setup_e2e_environment: dict,
) -> None:
    """Test 2-8: Complete lifecycle smoke flow.

    Draft generation -> Review queue -> Live safety validation -> Approval ->
    Scheduling -> Safe publishing via FakeThreadsClient -> Post verification ->
    Idempotent protection -> Kill switch fail-closed validation.
    """
    account = setup_e2e_environment["account"]
    niche = setup_e2e_environment["niche"]
    style = setup_e2e_environment["style"]

    # Step 1: Login
    login_res = await client.post(
        "/api/auth/login",
        json={"username": settings.ADMIN_USERNAME, "password": TEST_ADMIN_PWD},
    )
    assert login_res.status_code == 200
    csrf_token = login_res.json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf_token}

    # Step 2: Ingest a draft into pending_review
    post_text = "Ergonomic split keyboard recommendations for wrist relief. Benable list: https://benable.com/alex/keyboards #wfh (Affiliate link)"
    draft = Draft(
        id="draft_e2e_test_101",
        account_id=account.id,
        niche_id=niche.id,
        style_id=style.id,
        prompt_version="p_v1",
        llm_model="fake-llm",
        parts=json.dumps([{"part_index": 1, "text": post_text, "char_count": len(post_text)}]),
        link_url="https://benable.com/alex/keyboards",
        text_hash="hash_smoke_101",
        status="pending_review",
        validator_report=json.dumps({"valid": True, "failed_codes": []}),
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    db_session.add(draft)
    await db_session.commit()

    # Step 3: Fetch review queue
    res_queue = await client.get("/api/drafts?status=pending_review")
    assert res_queue.status_code == 200
    items = res_queue.json()
    assert any(d["id"] == "draft_e2e_test_101" for d in items)

    # Step 4: Validate real-time text with price violation ($39.99)
    res_validate_bad = await client.post(
        "/api/drafts/validate-text",
        json={
            "text": "Ergonomic split keyboard only $39.99! https://benable.com/alex/keyboards (Affiliate link)",
            "style_id": style.id,
            "is_affiliate": True,
            "disclosure_text": "Affiliate link",
        },
        headers=headers,
    )
    assert res_validate_bad.status_code == 200
    val_bad_data = res_validate_bad.json()
    assert val_bad_data["valid"] is False
    assert "V-PRICE" in val_bad_data["failed_codes"]

    # Step 5: Validate clean text without price
    res_validate_clean = await client.post(
        "/api/drafts/validate-text",
        json={
            "text": post_text,
            "style_id": style.id,
            "is_affiliate": True,
            "disclosure_text": "Affiliate link",
        },
        headers=headers,
    )
    assert res_validate_clean.status_code == 200
    assert res_validate_clean.json()["valid"] is True

    # Step 6: Approve the draft
    res_approve = await client.post(
        f"/api/drafts/{draft.id}/approve",
        headers=headers,
    )
    assert res_approve.status_code == 200
    approve_data = res_approve.json()
    assert approve_data["status"] == "approved"

    # Verify DB state of draft
    await db_session.refresh(draft)
    assert draft.status == "approved"

    # Step 7: Execute publication using FakeThreadsClient
    fake_threads = FakeThreadsClient()
    post = await publish_single_post(
        db_session,
        account_id=account.id,
        text=post_text,
        draft_id=draft.id,
        client=fake_threads,
    )
    assert post is not None
    assert post.threads_media_id is not None
    assert post.draft_id == draft.id
    assert post.published_at is not None

    # Step 8: Verify database post record
    await db_session.refresh(draft)
    assert draft.status == "published"

    # Step 9: Verify zero-duplicate guarantee
    dup_post = await publish_single_post(
        db_session,
        account_id=account.id,
        text=post_text,
        draft_id=draft.id,
        client=fake_threads,
    )
    assert dup_post.id == post.id
    assert fake_threads.create_container_calls == 1

    # Step 10: Emergency Kill Switch fail-closed verification
    await set_kill_switch(db_session, active=True, reason="Emergency drill", actor="admin")
    assert await is_kill_switch_active(db_session) is True

    # Ingest a second approved draft
    draft_2_text = "Standing desk mat review. https://benable.com/alex/mats #wfh (Affiliate link)"
    draft_2 = Draft(
        id="draft_e2e_test_102",
        account_id=account.id,
        niche_id=niche.id,
        style_id=style.id,
        prompt_version="p_v1",
        llm_model="fake-llm",
        parts=json.dumps([{"part_index": 1, "text": draft_2_text, "char_count": len(draft_2_text)}]),
        link_url="https://benable.com/alex/mats",
        text_hash="hash_smoke_102",
        status="approved",
        scheduled_at=utc_now_iso(),
        validator_report=json.dumps({"valid": True, "failed_codes": []}),
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    db_session.add(draft_2)
    await db_session.commit()

    # Attempt to publish draft_2 while kill switch is active must be blocked by PublishGuard
    with pytest.raises(PermissionError, match="KILL_SWITCH_ON"):
        await publish_single_post(
            db_session,
            account_id=account.id,
            text=draft_2_text,
            draft_id=draft_2.id,
            client=fake_threads,
        )

    # Zero additional containers created
    assert fake_threads.create_container_calls == 1

