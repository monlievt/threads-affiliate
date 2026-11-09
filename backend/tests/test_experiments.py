"""tests/test_experiments.py — Test suite for Experiment Module, Arms, and Allocation Planner (T-042).

Verifies:
1. Scientific validation & Single-variable rule:
   - 'niche_test': Variable is niche; style must remain constant across all arms.
   - 'style_test': Variable is style; niche must remain constant across all arms.
   - Minimum 2 arms required; target_posts >= 1.
2. State machine transitions & concurrency rules:
   - planned -> running -> completed | aborted.
   - Only 1 running experiment per phase.
3. Allocation Planner:
   - Balanced arm allocation (favors arm with lowest draft count).
   - Anti-streak / Consecutive arm avoidance.
   - Quota completion detection.
   - Interleaving of drafts by arm.
   - Randomization of posting times inside active hours.
4. API Endpoints:
   - GET /api/experiments, POST /api/experiments, GET /api/experiments/{id}.
   - PATCH /api/experiments/{id}/status, GET /api/experiments/{id}/progress.
   - POST /api/experiments/{id}/allocate-next.
"""

from __future__ import annotations

import json
from datetime import date
from zoneinfo import ZoneInfo
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, create_session_token
from app.db.models import Account, AuditLog, Draft, Experiment, ExperimentArm, Niche, Post, PostMetric, Style
from app.experiments.allocator import (
    interleave_drafts_by_arm,
    randomize_time_in_active_window,
    select_next_arm_for_generation,
)
from app.experiments.service import (
    create_experiment,
    get_experiment_progress,
    update_experiment_status,
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
# 1. Validation & Single Variable Rule Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_experiment_validation_rules(db_session: AsyncSession) -> None:
    # Pre-seed niches and styles
    n1 = Niche(id="niche_exp_1", name="Home & Kitchen", slug="home-kitchen-exp")
    n2 = Niche(id="niche_exp_2", name="Pet Supplies", slug="pet-supplies-exp")
    n3 = Niche(id="niche_exp_3", name="Desk Setup", slug="desk-setup-exp")
    s1 = Style(id="style_exp_1", name="curator", tone_rules="curator rules")
    s2 = Style(id="style_exp_2", name="quick_review", tone_rules="review rules")
    db_session.add_all([n1, n2, n3, s1, s2])
    await db_session.commit()

    # Error: less than 2 arms
    with pytest.raises(ValueError, match="at least 2 comparison arms"):
        await create_experiment(
            db_session,
            name="Single Arm Test",
            phase="niche_test",
            start_date="2026-11-10",
            arms_data=[{"label": "Arm 1", "niche_id": n1.id, "style_id": s1.id}],
        )

    # Error: invalid phase
    with pytest.raises(ValueError, match="Invalid phase"):
        await create_experiment(
            db_session,
            name="Bad Phase",
            phase="invalid_phase",
            start_date="2026-11-10",
            arms_data=[
                {"label": "Arm 1", "niche_id": n1.id},
                {"label": "Arm 2", "niche_id": n2.id},
            ],
        )

    # Error in niche_test: multiple styles across arms violates single variable rule
    with pytest.raises(ValueError, match="single variable rule"):
        await create_experiment(
            db_session,
            name="Niche Test Bad Styles",
            phase="niche_test",
            start_date="2026-11-10",
            arms_data=[
                {"label": "Arm 1", "niche_id": n1.id, "style_id": s1.id},
                {"label": "Arm 2", "niche_id": n2.id, "style_id": s2.id},
            ],
        )

    # Error in niche_test: duplicate niches across arms
    with pytest.raises(ValueError, match="distinct niche"):
        await create_experiment(
            db_session,
            name="Niche Test Duplicate Niches",
            phase="niche_test",
            start_date="2026-11-10",
            arms_data=[
                {"label": "Arm 1", "niche_id": n1.id, "style_id": s1.id},
                {"label": "Arm 2", "niche_id": n1.id, "style_id": s1.id},
            ],
        )

    # Success in niche_test: 3 distinct niches, 1 constant style
    exp = await create_experiment(
        db_session,
        name="Phase 1 Niche Test Valid",
        phase="niche_test",
        start_date="2026-11-10",
        arms_data=[
            {"label": "Home", "niche_id": n1.id, "style_id": s1.id, "target_posts": 12},
            {"label": "Pet", "niche_id": n2.id, "style_id": s1.id, "target_posts": 12},
            {"label": "Desk", "niche_id": n3.id, "style_id": s1.id, "target_posts": 12},
        ],
    )
    assert exp.status == "planned"
    assert exp.phase == "niche_test"


# ---------------------------------------------------------------------------
# 2. State Machine & Concurrency Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_experiment_lifecycle_and_concurrency(db_session: AsyncSession) -> None:
    n1 = Niche(id="n_life_1", name="Niche L1", slug="n-l1")
    n2 = Niche(id="n_life_2", name="Niche L2", slug="n-l2")
    s1 = Style(id="s_life_1", name="curator", tone_rules="curator rules")
    db_session.add_all([n1, n2, s1])
    await db_session.commit()

    exp1 = await create_experiment(
        db_session,
        name="Exp 1",
        phase="niche_test",
        start_date="2026-11-10",
        arms_data=[
            {"label": "Arm 1", "niche_id": n1.id, "style_id": s1.id},
            {"label": "Arm 2", "niche_id": n2.id, "style_id": s1.id},
        ],
    )
    exp2 = await create_experiment(
        db_session,
        name="Exp 2",
        phase="niche_test",
        start_date="2026-11-10",
        arms_data=[
            {"label": "Arm 1", "niche_id": n1.id, "style_id": s1.id},
            {"label": "Arm 2", "niche_id": n2.id, "style_id": s1.id},
        ],
    )

    # 1. Start Exp 1 -> running
    await update_experiment_status(db_session, exp1.id, "running")

    # 2. Try starting Exp 2 in same phase -> rejected by concurrency rule
    with pytest.raises(ValueError, match="Only one running experiment per phase is allowed"):
        await update_experiment_status(db_session, exp2.id, "running")

    # 3. Complete Exp 1 -> completed
    await update_experiment_status(db_session, exp1.id, "completed")

    # 4. Now Exp 2 can be started
    await update_experiment_status(db_session, exp2.id, "running")

    # 5. Invalid transition: completed -> running is rejected
    with pytest.raises(ValueError, match="Cannot transition experiment from 'completed'"):
        await update_experiment_status(db_session, exp1.id, "running")


# ---------------------------------------------------------------------------
# 3. Arm Allocation & Anti-Streak Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_arm_allocation_and_anti_streak(db_session: AsyncSession) -> None:
    # Setup account and experiment
    acc = Account(id="acc_alloc_test", username="tester")
    db_session.add(acc)

    n1 = Niche(id="n_alloc_1", name="Niche 1", slug="n-a1")
    n2 = Niche(id="n_alloc_2", name="Niche 2", slug="n-a2")
    s1 = Style(id="s_alloc_1", name="curator", tone_rules="curator rules")
    db_session.add_all([n1, n2, s1])
    await db_session.commit()

    exp = await create_experiment(
        db_session,
        name="Allocation Test",
        phase="niche_test",
        start_date="2026-11-10",
        arms_data=[
            {"label": "Arm 1", "niche_id": n1.id, "style_id": s1.id, "target_posts": 2},
            {"label": "Arm 2", "niche_id": n2.id, "style_id": s1.id, "target_posts": 2},
        ],
    )
    await update_experiment_status(db_session, exp.id, "running")

    arms_res = await db_session.execute(
        select(ExperimentArm).where(ExperimentArm.experiment_id == exp.id).order_by(ExperimentArm.label)
    )
    arms = arms_res.scalars().all()
    arm1, arm2 = arms[0], arms[1]

    # Allocation 1: both 0 drafts -> picks Arm 1
    chosen, reason = await select_next_arm_for_generation(db_session, exp.id)
    assert chosen is not None
    assert chosen.id == arm1.id

    # Simulate creating draft for Arm 1
    d1 = Draft(
        id="draft_alloc_1",
        account_id=acc.id,
        arm_id=arm1.id,
        niche_id=n1.id,
        style_id=s1.id,
        prompt_version="p_v1",
        llm_model="gemini-pro",
        parts=json.dumps([{"text": "Draft 1"}]),
        status="approved",
    )
    db_session.add(d1)
    await db_session.commit()

    # Allocation 2: Arm 1 has 1 draft, Arm 2 has 0 -> picks Arm 2 (load balance)
    chosen2, _ = await select_next_arm_for_generation(db_session, exp.id, last_arm_id=arm1.id)
    assert chosen2 is not None
    assert chosen2.id == arm2.id

    # Simulate creating draft for Arm 2
    d2 = Draft(
        id="draft_alloc_2",
        account_id=acc.id,
        arm_id=arm2.id,
        niche_id=n2.id,
        style_id=s1.id,
        prompt_version="p_v1",
        llm_model="gemini-pro",
        parts=json.dumps([{"text": "Draft 2"}]),
        status="approved",
    )
    db_session.add(d2)
    await db_session.commit()

    # Allocation 3: both have 1 draft. If last_arm_id is Arm 2, anti-streak picks Arm 1!
    chosen3, _ = await select_next_arm_for_generation(
        db_session, exp.id, last_arm_id=arm2.id, last_niche_id=n2.id
    )
    assert chosen3 is not None
    assert chosen3.id == arm1.id

    # Fill up both arms to target_posts = 2
    d3 = Draft(
        id="draft_alloc_3",
        account_id=acc.id,
        arm_id=arm1.id,
        niche_id=n1.id,
        style_id=s1.id,
        prompt_version="p_v1",
        llm_model="gemini-pro",
        parts=json.dumps([{"text": "Draft 3"}]),
        status="approved",
    )
    d4 = Draft(
        id="draft_alloc_4",
        account_id=acc.id,
        arm_id=arm2.id,
        niche_id=n2.id,
        style_id=s1.id,
        prompt_version="p_v1",
        llm_model="gemini-pro",
        parts=json.dumps([{"text": "Draft 4"}]),
        status="approved",
    )
    db_session.add_all([d3, d4])
    await db_session.commit()

    # Allocation 4: all arms reached target
    chosen4, reason4 = await select_next_arm_for_generation(db_session, exp.id)
    assert chosen4 is None
    assert "All arms have reached their target" in reason4


def test_interleaving_and_time_randomization() -> None:
    # Test interleave_drafts_by_arm
    d1 = Draft(id="d1", arm_id="arm_A")
    d2 = Draft(id="d2", arm_id="arm_A")
    d3 = Draft(id="d3", arm_id="arm_B")
    d4 = Draft(id="d4", arm_id="arm_B")

    interleaved = interleave_drafts_by_arm([d1, d2, d3, d4])
    # Interleaved must alternate arm_A, arm_B, arm_A, arm_B
    arm_sequence = [d.arm_id for d in interleaved]
    assert arm_sequence == ["arm_A", "arm_B", "arm_A", "arm_B"]

    # Test randomize_time_in_active_window
    tz = ZoneInfo("America/New_York")
    d = date(2026, 11, 10)
    slot1 = randomize_time_in_active_window(d, start_hour=9, end_hour=21, slot_index=0, total_slots_today=3, tz=tz)
    slot2 = randomize_time_in_active_window(d, start_hour=9, end_hour=21, slot_index=1, total_slots_today=3, tz=tz)
    slot3 = randomize_time_in_active_window(d, start_hour=9, end_hour=21, slot_index=2, total_slots_today=3, tz=tz)

    # Convert back to local
    l1 = slot1.astimezone(tz)
    l2 = slot2.astimezone(tz)
    l3 = slot3.astimezone(tz)

    assert 9 <= l1.hour <= 20
    assert 9 <= l2.hour <= 20
    assert 9 <= l3.hour <= 20


# ---------------------------------------------------------------------------
# 4. API Endpoints Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_experiments_crud_and_progress(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    n1 = Niche(id="niche_api_1", name="Desk Tech", slug="desk-tech")
    n2 = Niche(id="niche_api_2", name="Coffee Gear", slug="coffee-gear")
    s1 = Style(id="style_api_1", name="curator", tone_rules="curator rules")
    db_session.add_all([n1, n2, s1])
    await db_session.commit()

    # 1. POST create experiment
    create_payload = {
        "name": "Phase 1 Niche Trial",
        "phase": "niche_test",
        "start_date": "2026-11-10",
        "arms": [
            {"label": "Desk Arm", "niche_id": n1.id, "style_id": s1.id, "target_posts": 12},
            {"label": "Coffee Arm", "niche_id": n2.id, "style_id": s1.id, "target_posts": 12},
        ],
    }
    c_res = await async_client.post(
        "/api/experiments", json=create_payload, headers=headers, cookies=cookies
    )
    assert c_res.status_code == 201
    exp_data = c_res.json()
    exp_id = exp_data["id"]
    assert exp_data["name"] == "Phase 1 Niche Trial"
    assert exp_data["status"] == "planned"
    assert len(exp_data["arms"]) == 2

    # 2. GET /api/experiments
    list_res = await async_client.get(
        "/api/experiments", headers=headers, cookies=cookies
    )
    assert list_res.status_code == 200
    assert any(e["id"] == exp_id for e in list_res.json())

    # 3. GET /api/experiments/{id}
    detail_res = await async_client.get(
        f"/api/experiments/{exp_id}", headers=headers, cookies=cookies
    )
    assert detail_res.status_code == 200
    assert detail_res.json()["id"] == exp_id

    # 4. PATCH /api/experiments/{id}/status -> running
    status_res = await async_client.patch(
        f"/api/experiments/{exp_id}/status",
        json={"status_update": "running"},
        headers=headers,
        cookies=cookies,
    )
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "running"

    # 5. GET /api/experiments/{id}/progress
    prog_res = await async_client.get(
        f"/api/experiments/{exp_id}/progress", headers=headers, cookies=cookies
    )
    assert prog_res.status_code == 200
    prog_data = prog_res.json()
    assert prog_data["total_target_posts"] == 24
    assert prog_data["total_published_posts"] == 0
    assert prog_data["overall_progress_pct"] == 0.0
    assert len(prog_data["arms"]) == 2

    # 6. POST /api/experiments/{id}/allocate-next
    alloc_res = await async_client.post(
        f"/api/experiments/{exp_id}/allocate-next",
        json={},
        headers=headers,
        cookies=cookies,
    )
    assert alloc_res.status_code == 200
    alloc_data = alloc_res.json()
    assert alloc_data["has_eligible_arm"] is True
    assert alloc_data["recommended_arm"] is not None
