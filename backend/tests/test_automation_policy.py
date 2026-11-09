"""tests/test_automation_policy.py — Test suite for Automation Modes, Full-Auto Eligibility, and Auto-Downgrade (T-050).

Verifies docs/06 §6 compliance:
1. determine_draft_initial_status:
   - manual_approve mode -> 100% pending_review.
   - full_auto mode -> 100% approved.
   - auto_sampled mode -> probabilistic sampling based on sample_review_pct.
   - failing validation -> rejected_auto.
2. evaluate_auto_downgrade:
   - 1 critical incident in 7 days -> auto-downgrades to manual_approve.
   - 2 warning incidents in 7 days -> auto-downgrades to manual_approve.
   - 1 warning incident -> no downgrade.
   - Incidents older than 7 days -> no downgrade.
   - Audit trail and new incident recorded on downgrade.
3. evaluate_full_auto_eligibility:
   - Tests all 5 criteria over 14 days window:
     * 0 critical incidents
     * Validator rejection rate < 2% (min 20 drafts)
     * Operator rejection rate < 15% on >= 40 reviewed drafts
     * Threads token valid & Kill switch OFF
     * Worker heartbeat healthy (< 120s)
4. Integration with ContentEngine draft generation.
5. Integration with API endpoints (GET /api/system/full-auto-eligibility & PUT /api/system/account).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.content.engine import ContentEngine
from app.content.llm.fake import FakeLLMProvider
from app.core.clock import utc_now, utc_now_iso
from app.core.crypto import encrypt_token
from app.core.security import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, create_session_token
from app.db.models import Account, AuditLog, Draft, Incident, Niche, Persona, Product, Style
from app.scheduler.heartbeat import record_worker_heartbeat
from app.safety.automation_policy import (
    determine_draft_initial_status,
    evaluate_auto_downgrade,
    evaluate_full_auto_eligibility,
)


def _get_auth_headers_and_cookies() -> tuple[dict[str, str], dict[str, str]]:
    token, csrf_token = create_session_token("admin")
    headers = {"X-CSRF-Token": csrf_token}
    cookies = {
        SESSION_COOKIE_NAME: token,
        CSRF_COOKIE_NAME: csrf_token,
    }
    return headers, cookies


# ---------------------------------------------------------------------------
# 1. determine_draft_initial_status Unit Tests
# ---------------------------------------------------------------------------

def test_determine_draft_initial_status() -> None:
    # 1. Validation failed
    acc_manual = Account(id="acc_m", automation_mode="manual_approve")
    status, reason = determine_draft_initial_status(acc_manual, val_passed=False, reject_reason="bad words")
    assert status == "rejected_auto"
    assert reason == "bad words"

    # 2. Manual approve mode -> pending_review
    status_m, reason_m = determine_draft_initial_status(acc_manual, val_passed=True)
    assert status_m == "pending_review"
    assert reason_m is None

    # 3. Full auto mode -> approved
    acc_auto = Account(id="acc_fa", automation_mode="full_auto")
    status_fa, reason_fa = determine_draft_initial_status(acc_auto, val_passed=True)
    assert status_fa == "approved"
    assert "full_auto" in (reason_fa or "")

    # 4. Auto sampled mode
    acc_sampled = Account(id="acc_s", automation_mode="auto_sampled", sample_review_pct=50)
    # Sampling produces either 'pending_review' or 'approved'
    outcomes = set()
    for _ in range(50):
        st, _ = determine_draft_initial_status(acc_sampled, val_passed=True)
        outcomes.add(st)
    assert outcomes == {"pending_review", "approved"}


# ---------------------------------------------------------------------------
# 2. evaluate_auto_downgrade Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_downgrade_critical_incident(db_session: AsyncSession) -> None:
    acc = Account(id="acc_down_1", username="auto_user", automation_mode="full_auto")
    db_session.add(acc)
    await db_session.commit()

    # 1. Initially 0 incidents -> no downgrade
    downgraded, _ = await evaluate_auto_downgrade(db_session, acc)
    assert downgraded is False
    assert acc.automation_mode == "full_auto"

    # 2. 1 Critical incident in past 7 days -> triggers downgrade
    inc = Incident(
        id="inc_crit_1",
        account_id=acc.id,
        code="UNAUTHORIZED_API_CALL",
        severity="critical",
        detail="Rate limit anomaly detected",
        created_at=utc_now_iso(),
    )
    db_session.add(inc)
    await db_session.commit()

    downgraded2, reason2 = await evaluate_auto_downgrade(db_session, acc)
    assert downgraded2 is True
    assert "critical" in (reason2 or "")
    assert acc.automation_mode == "manual_approve"

    # 3. Verify audit log entry
    audit_res = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "auto_downgrade")
    )
    audit = audit_res.scalar_one_or_none()
    assert audit is not None
    assert audit.entity == "accounts"


@pytest.mark.asyncio
async def test_auto_downgrade_warning_incidents(db_session: AsyncSession) -> None:
    acc = Account(id="acc_down_2", username="sample_user", automation_mode="auto_sampled")
    db_session.add(acc)

    # 1 warning incident -> does NOT trigger downgrade (threshold is 2)
    inc1 = Incident(
        id="inc_warn_1",
        account_id=acc.id,
        code="JITTER_EXCEEDED",
        severity="warning",
        created_at=utc_now_iso(),
    )
    db_session.add(inc1)
    await db_session.commit()

    d1, _ = await evaluate_auto_downgrade(db_session, acc)
    assert d1 is False
    assert acc.automation_mode == "auto_sampled"

    # Second warning incident -> triggers downgrade
    inc2 = Incident(
        id="inc_warn_2",
        account_id=acc.id,
        code="TOKEN_REFRESH_WARNING",
        severity="warning",
        created_at=utc_now_iso(),
    )
    db_session.add(inc2)
    await db_session.commit()

    d2, reason2 = await evaluate_auto_downgrade(db_session, acc)
    assert d2 is True
    assert "2 insiden warning" in (reason2 or "")
    assert acc.automation_mode == "manual_approve"


@pytest.mark.asyncio
async def test_auto_downgrade_ignores_old_incidents(db_session: AsyncSession) -> None:
    acc = Account(id="acc_down_3", username="old_user", automation_mode="full_auto")
    db_session.add(acc)

    # Incident from 10 days ago (older than 7 days)
    old_time = (utc_now() - timedelta(days=10)).isoformat()
    old_inc = Incident(
        id="inc_old_crit",
        account_id=acc.id,
        code="OLD_CRITICAL",
        severity="critical",
        created_at=old_time,
    )
    db_session.add(old_inc)
    await db_session.commit()

    downgraded, _ = await evaluate_auto_downgrade(db_session, acc)
    assert downgraded is False
    assert acc.automation_mode == "full_auto"


# ---------------------------------------------------------------------------
# 3. evaluate_full_auto_eligibility Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_auto_eligibility_all_criteria(db_session: AsyncSession) -> None:
    now = utc_now()
    valid_token = encrypt_token("threads_token_secret_xyz")
    expiry = (now + timedelta(days=40)).isoformat()

    acc = Account(
        id="acc_elig_test",
        username="pro_creator",
        automation_mode="manual_approve",
        token_encrypted=valid_token,
        token_expires_at=expiry,
    )
    db_session.add(acc)

    # 1. Fresh account with 0 posts -> not eligible (fails validator & operator counts)
    res_fresh = await evaluate_full_auto_eligibility(db_session, acc)
    assert res_fresh.eligible is False
    assert res_fresh.criteria["validator_rejection_rate"].passed is False
    assert res_fresh.criteria["operator_rejection_rate"].passed is False

    # 2. Add healthy heartbeat
    await record_worker_heartbeat(db_session, "test_worker_1")

    # 3. Add 45 approved drafts (low operator rejection < 15%)
    # and 45 total generated with 0 auto rejected (< 2%)
    for i in range(45):
        d = Draft(
            id=f"d_elig_{i}",
            account_id=acc.id,
            kind="post",
            prompt_version="p_v1",
            llm_model="gemini-pro",
            parts=json.dumps([{"text": f"Healthy post {i}"}]),
            status="approved",
            created_at=(now - timedelta(days=2)).isoformat(),
        )
        db_session.add(d)

    await db_session.commit()

    # Now all 5 criteria should pass!
    res_ready = await evaluate_full_auto_eligibility(db_session, acc)
    assert res_ready.criteria["zero_critical_incidents"].passed is True
    assert res_ready.criteria["validator_rejection_rate"].passed is True
    assert res_ready.criteria["operator_rejection_rate"].passed is True
    assert res_ready.criteria["account_and_killswitch_ready"].passed is True
    assert res_ready.criteria["worker_heartbeat_healthy"].passed is True
    assert res_ready.eligible is True


# ---------------------------------------------------------------------------
# 4. ContentEngine Integration with Automation Modes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_content_engine_auto_approval_in_full_auto(db_session: AsyncSession) -> None:
    acc = Account(id="acc_ce_auto", username="ce_user", automation_mode="full_auto")
    niche = Niche(id="n_ce_auto", name="Coffee", slug="coffee-ce")
    style = Style(id="s_ce_auto", name="curator", tone_rules="curator rules", max_chars=300)
    persona = Persona(id="p_ce_auto", account_id=acc.id, name="Alex", voice="casual", disclosure_text="[Affiliate link]")
    prod = Product(id="prod_ce_auto", niche_id=niche.id, title="Coffee Grinder", benable_url="https://benable.com/c/grind")

    db_session.add_all([acc, niche, style, persona, prod])
    await db_session.commit()

    fake_json = json.dumps({
        "variants": [
            {
                "parts": ["Check out this neat manual coffee grinder. [Affiliate link]"],
                "has_link": True,
                "link_placement": "in_post",
                "angle": "curator",
                "hook_type": "tip",
            }
        ]
    })
    engine = ContentEngine(llm_provider=FakeLLMProvider(canned_response=fake_json))

    drafts = await engine.generate_drafts(
        db_session,
        account_id=acc.id,
        niche_id=niche.id,
        style_id=style.id,
        product_id=prod.id,
        num_variants=1,
    )

    assert len(drafts) == 1
    # Because account is in full_auto, passing draft is automatically approved!
    assert drafts[0].status == "approved"
    assert drafts[0].reviewed_at is not None


# ---------------------------------------------------------------------------
# 5. API Endpoints Integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_full_auto_rejection_when_ineligible(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    acc = Account(id="acc_api_sys", username="api_user", automation_mode="manual_approve")
    db_session.add(acc)
    await db_session.commit()

    # 1. GET /api/system/full-auto-eligibility
    res_elig = await async_client.get(
        "/api/system/full-auto-eligibility", headers=headers, cookies=cookies
    )
    assert res_elig.status_code == 200
    data_elig = res_elig.json()
    assert "eligible" in data_elig
    assert "criteria" in data_elig

    # 2. PUT /api/system/account attempting to set full_auto when ineligible -> 422 rejected!
    res_switch = await async_client.put(
        "/api/system/account",
        json={"automation_mode": "full_auto"},
        headers=headers,
        cookies=cookies,
    )
    assert res_switch.status_code == 422
    assert "full_auto ditolak" in res_switch.json()["detail"]["message"]
