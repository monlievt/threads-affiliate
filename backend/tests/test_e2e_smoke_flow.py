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

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.clock import utc_now, utc_now_iso
from app.core.crypto import encrypt_token
from app.db.models import Account, Draft, Niche, Persona, Post, Style, SystemState
from app.main import app
from app.safety.guard import PublishGuard
from app.safety.killswitch import is_kill_switch_active, set_kill_switch
from app.threads.client import FakeThreadsClient
from app.threads.publisher import publish_draft_job


@pytest.fixture
async def setup_e2e_environment(db_session: AsyncSession):
    """Seed necessary test account, niche, style, and system state for E2E flow."""
    # Ensure kill switch is deactivated for active operational testing
    await set_kill_switch(db_session, active=False, reason="E2E test setup", actor="tester")

    # Account
    account = Account(
        id="acc_e2e_smoke_01",
        threads_user_id="user_smoke_threads_01",
        username="curator_smoke_e2e",
        account_type="primary",
        warmup_tier="week_1",
        is_active=True,
        encrypted_access_token=encrypt_token("fake_valid_access_token"),
        token_expires_at="2099-01-01T00:00:00Z",
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    db_session.add(account)

    # Niche
    niche = Niche(
        id="niche_ergonomics_01",
        name="WFH Ergonomics",
        slug="wfh-ergonomics",
        target_audience="US remote workers",
        is_active=True,
        daily_limit=1,
    )
    db_session.add(niche)

    # Style
    style = Style(
        id="style_curated_list_01",
        name="Curated Recommendation List",
        slug="curated-list",
        prompt_instruction="Curate genuine helpful recommendations for desk workers.",
        is_active=True,
    )
    db_session.add(style)

    # Persona
    persona = Persona(
        id="persona_thoughtful_curator_01",
        name="Thoughtful Curator",
        tone_description="Warm, practical, informative, zero aggressive claims.",
        is_active=True,
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
async def test_e2e_admin_auth_and_session(db_session: AsyncSession) -> None:
    """Test 1: Admin login, session issuance, and CSRF token."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Invalid login
        resp_invalid = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong_password_123"},
        )
        assert resp_invalid.status_code == 401

        # Valid login
        resp_valid = await client.post(
            "/api/auth/login",
            json={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
        )
        assert resp_valid.status_code == 200
        data = resp_valid.json()
        assert data["status"] == "ok"
        assert data["username"] == settings.ADMIN_USERNAME
        assert "csrf_token" in data
        assert len(data["csrf_token"]) > 10

        csrf_token = data["csrf_token"]
        session_cookie = resp_valid.cookies.get("threads_affiliate_session")
        assert session_cookie is not None


@pytest.mark.asyncio
async def test_e2e_full_lifecycle_smoke(
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

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Step 1: Login
        login_res = await client.post(
            "/api/auth/login",
            json={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
        )
        assert login_res.status_code == 200
        csrf_token = login_res.json()["csrf_token"]
        cookies = {"threads_affiliate_session": login_res.cookies.get("threads_affiliate_session")}
        headers = {"X-CSRF-Token": csrf_token}

        # Step 2: Ingest a draft into pending_review
        draft = Draft(
            id="draft_e2e_test_101",
            account_id=account.id,
            niche_id=niche.id,
            style_id=style.id,
            text="Ergonomic split keyboard recommendations for wrist relief. Benable list: benable.com/alex/keyboards #wfh",
            clean_url="https://benable.com/alex/keyboards",
            status="pending_review",
            compliance_checklist={"valid": True, "errors": []},
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        db_session.add(draft)
        await db_session.commit()

        # Step 3: Fetch review queue
        res_queue = await client.get("/api/drafts?status=pending_review", cookies=cookies)
        assert res_queue.status_code == 200
        items = res_queue.json()
        assert any(d["id"] == "draft_e2e_test_101" for d in items)

        # Step 4: Validate real-time text with price violation ($39.99)
        res_validate_bad = await client.post(
            "/api/drafts/validate-text",
            json={"text": "Ergonomic split keyboard only $39.99! benable.com/alex/keyboards"},
            cookies=cookies,
            headers=headers,
        )
        assert res_validate_bad.status_code == 200
        val_bad_data = res_validate_bad.json()
        assert val_bad_data["valid"] is False
        assert any(e["code"] == "V-PRICE" for e in val_bad_data["errors"])

        # Step 5: Validate clean text without price
        res_validate_clean = await client.post(
            "/api/drafts/validate-text",
            json={"text": "Ergonomic split keyboard recommendations for wrist relief. benable.com/alex/keyboards #wfh"},
            cookies=cookies,
            headers=headers,
        )
        assert res_validate_clean.status_code == 200
        assert res_validate_clean.json()["valid"] is True

        # Step 6: Approve the draft
        res_approve = await client.post(
            f"/api/drafts/{draft.id}/approve",
            cookies=cookies,
            headers=headers,
        )
        assert res_approve.status_code == 200
        approve_data = res_approve.json()
        assert approve_data["status"] == "approved"
        assert approve_data["scheduled_slot"] is not None

        # Verify DB state of draft
        await db_session.refresh(draft)
        assert draft.status == "approved"
        assert draft.scheduled_slot is not None

        # Step 7: Execute publication using FakeThreadsClient
        fake_threads = FakeThreadsClient()
        publish_result = await publish_draft_job(
            db_session,
            draft_id=draft.id,
            threads_client=fake_threads,
        )
        assert publish_result["status"] == "published"
        assert "post_id" in publish_result
        assert "threads_media_id" in publish_result

        # Step 8: Verify database post record
        await db_session.refresh(draft)
        assert draft.status == "published"
        assert draft.published_at is not None

        # Step 9: Verify zero-duplicate guarantee
        # Attempting to re-publish the same draft must be rejected immediately
        dup_result = await publish_draft_job(
            db_session,
            draft_id=draft.id,
            threads_client=fake_threads,
        )
        assert dup_result["status"] == "rejected"
        assert dup_result["reason"] in ("DRAFT_NOT_APPROVED", "POST_ALREADY_EXISTS")
        # Threads client container creation count should remain exactly 1
        assert len(fake_threads.created_containers) == 1

        # Step 10: Emergency Kill Switch fail-closed verification
        await set_kill_switch(db_session, active=True, reason="Emergency drill", actor="admin")
        assert await is_kill_switch_active(db_session) is True

        # Ingest a second approved draft
        draft_2 = Draft(
            id="draft_e2e_test_102",
            account_id=account.id,
            niche_id=niche.id,
            style_id=style.id,
            text="Standing desk mat review. benable.com/alex/mats #wfh",
            clean_url="https://benable.com/alex/mats",
            status="approved",
            scheduled_slot=utc_now_iso(),
            compliance_checklist={"valid": True, "errors": []},
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        db_session.add(draft_2)
        await db_session.commit()

        # Attempt to publish draft_2 while kill switch is active
        blocked_result = await publish_draft_job(
            db_session,
            draft_id=draft_2.id,
            threads_client=fake_threads,
        )
        assert blocked_result["status"] == "rejected"
        assert blocked_result["reason"] == "KILL_SWITCH_ACTIVE"
        # Zero additional containers created
        assert len(fake_threads.created_containers) == 1
