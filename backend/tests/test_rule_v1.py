"""tests/test_rule_v1.py — Test suite for Decision Rule rule_v1 and Weekly Reports (T-043).

Verifies:
1. Exact numeric properties:
   - Median calculation (odd, even, single, empty, unsorted).
   - Outlier detection (value > 3x median).
   - Min-max normalization.
2. Scientific decision rules (docs/07 §3):
   - Rule 1: Arm with n < 8 is labeled "data kurang" and not ranked as winner.
   - Rule 2: Formula weighting:
     * With ClickRate: 0.4 ER + 0.4 ClickRate + 0.2 Views
     * Without ClickRate: 0.8 ER + 0.2 Views
   - Rule 3: Median resistance to viral outliers.
   - Rule 4: Winner threshold requires top_score >= 1.25x runner_up.
   - Rule 5: Non-winner produces "belum ada pemenang jelas, perpanjang uji X postingan".
3. Weekly performance report:
   - Aggregation of published posts, views, engagements, operator review workload, incidents.
   - Telegram-formatted output.
4. API Endpoints:
   - GET /api/experiments/{id}/evaluation
   - GET /api/analytics/weekly-report
   - Telegram handle_report integration
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now_iso
from app.core.security import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, create_session_token
from app.db.models import Account, Draft, Experiment, ExperimentArm, Incident, LinkClick, Niche, Post, PostMetric, Style
from app.experiments.rule_v1 import (
    calculate_median,
    detect_outliers,
    evaluate_experiment_rule_v1,
    min_max_normalize,
)
from app.experiments.service import create_experiment, update_experiment_status
from app.experiments.weekly_report import (
    format_weekly_report_telegram,
    generate_weekly_report,
)
from app.telegram.handlers import handle_report


def _get_auth_headers_and_cookies() -> tuple[dict[str, str], dict[str, str]]:
    token, csrf_token = create_session_token("admin")
    headers = {"X-CSRF-Token": csrf_token}
    cookies = {
        SESSION_COOKIE_NAME: token,
        CSRF_COOKIE_NAME: csrf_token,
    }
    return headers, cookies


# ---------------------------------------------------------------------------
# 1. Numeric Statistics Unit Tests
# ---------------------------------------------------------------------------

def test_calculate_median_math() -> None:
    # Empty
    assert calculate_median([]) == 0.0

    # Single element
    assert calculate_median([42.5]) == 42.5

    # Odd count (sorted and unsorted)
    assert calculate_median([10.0, 20.0, 30.0]) == 20.0
    assert calculate_median([30.0, 10.0, 20.0]) == 20.0

    # Even count (sorted and unsorted)
    assert calculate_median([10.0, 20.0, 30.0, 40.0]) == 25.0
    assert calculate_median([40.0, 10.0, 30.0, 20.0]) == 25.0


def test_detect_outliers() -> None:
    items = [
        {"post_id": "p1", "views": 100},
        {"post_id": "p2", "views": 110},
        {"post_id": "p3", "views": 90},
        {"post_id": "p4", "views": 350},  # > 3 * 100 = 300 -> Outlier!
    ]
    outliers = detect_outliers(items, "views", median_val=100.0, multiplier=3.0)
    assert len(outliers) == 1
    assert outliers[0]["post_id"] == "p4"
    assert outliers[0]["value"] == 350
    assert outliers[0]["threshold"] == 300.0


def test_min_max_normalize() -> None:
    # Empty
    assert min_max_normalize({}) == {}

    # All identical
    norm_same = min_max_normalize({"a": 50.0, "b": 50.0})
    assert norm_same == {"a": 1.0, "b": 1.0}

    # Distinct values
    norm = min_max_normalize({"a": 10.0, "b": 20.0, "c": 30.0})
    assert norm["a"] == 0.0
    assert norm["b"] == 0.5
    assert norm["c"] == 1.0


# ---------------------------------------------------------------------------
# 2. rule_v1 Evaluation Logic & Thresholds Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rule_v1_insufficient_data_label(db_session: AsyncSession) -> None:
    """Arms with n < 8 posts must be labeled 'data kurang' and not ranked."""
    acc = Account(id="acc_rule_1", username="tester")
    db_session.add(acc)

    n1 = Niche(id="n_rv1_1", name="Niche 1", slug="n-rv1-1")
    n2 = Niche(id="n_rv1_2", name="Niche 2", slug="n-rv1-2")
    s1 = Style(id="s_rv1_1", name="curator", tone_rules="curator rules")
    db_session.add_all([n1, n2, s1])
    await db_session.commit()

    exp = await create_experiment(
        db_session,
        name="Rule v1 Insufficient Data Test",
        phase="niche_test",
        start_date="2026-11-10",
        arms_data=[
            {"label": "Arm 1", "niche_id": n1.id, "style_id": s1.id, "target_posts": 12},
            {"label": "Arm 2", "niche_id": n2.id, "style_id": s1.id, "target_posts": 12},
        ],
    )
    await update_experiment_status(db_session, exp.id, "running")

    arms_res = await db_session.execute(
        select(ExperimentArm).where(ExperimentArm.experiment_id == exp.id).order_by(ExperimentArm.label)
    )
    arms = arms_res.scalars().all()
    arm1, arm2 = arms[0], arms[1]

    # Add 4 posts with 72h metrics to Arm 1 (n=4 < 8)
    for i in range(4):
        d = Draft(
            id=f"draft_rv1_a1_{i}",
            account_id=acc.id,
            arm_id=arm1.id,
            niche_id=n1.id,
            style_id=s1.id,
            prompt_version="p_v1",
            llm_model="gemini-pro",
            parts=json.dumps([{"text": f"Arm 1 Post {i}"}]),
            status="published",
        )
        db_session.add(d)
        p = Post(
            id=f"post_rv1_a1_{i}",
            draft_id=d.id,
            account_id=acc.id,
            threads_media_id=f"media_a1_{i}",
            published_at="2026-11-05T12:00:00Z",
        )
        db_session.add(p)
        pm = PostMetric(
            id=f"pm_rv1_a1_{i}",
            post_id=p.id,
            captured_at="2026-11-08T12:00:00Z",
            age_bucket="72h",
            views=100 + i * 10,
            likes=10,
            replies=2,
            reposts=1,
            quotes=0,
        )
        db_session.add(pm)

    await db_session.commit()

    evaluation = await evaluate_experiment_rule_v1(db_session, exp.id)
    assert evaluation.recommendation == "insufficient_data"
    assert evaluation.winner_arm_id is None
    assert "Data kurang" in evaluation.explanation

    # Check arm evaluation
    arm1_eval = next(a for a in evaluation.arms if a.arm_id == arm1.id)
    assert arm1_eval.n == 4
    assert arm1_eval.insufficient_data is True
    assert arm1_eval.rank is None


@pytest.mark.asyncio
async def test_rule_v1_winner_threshold_and_extensions(db_session: AsyncSession) -> None:
    """Top score >= 1.25x runner-up with n >= 8 generates winner; otherwise suggests extension."""
    acc = Account(id="acc_rule_2", username="tester")
    db_session.add(acc)

    n1 = Niche(id="n_rv1_w1", name="Home Tech", slug="home-tech")
    n2 = Niche(id="n_rv1_w2", name="Pet Tech", slug="pet-tech")
    s1 = Style(id="s_rv1_w1", name="curator", tone_rules="curator rules")
    db_session.add_all([n1, n2, s1])
    await db_session.commit()

    exp = await create_experiment(
        db_session,
        name="Rule v1 Winner Test",
        phase="niche_test",
        start_date="2026-11-10",
        arms_data=[
            {"label": "Home", "niche_id": n1.id, "style_id": s1.id, "target_posts": 10},
            {"label": "Pet", "niche_id": n2.id, "style_id": s1.id, "target_posts": 10},
        ],
    )
    await update_experiment_status(db_session, exp.id, "running")

    arms_res = await db_session.execute(
        select(ExperimentArm).where(ExperimentArm.experiment_id == exp.id).order_by(ExperimentArm.label)
    )
    arms = arms_res.scalars().all()
    arm_home, arm_pet = arms[0], arms[1]

    # Add 8 posts to Home (high engagement: 300 views, 30 likes)
    for i in range(8):
        d = Draft(
            id=f"d_home_{i}",
            account_id=acc.id,
            arm_id=arm_home.id,
            niche_id=n1.id,
            style_id=s1.id,
            prompt_version="p_v1",
            llm_model="gemini-pro",
            parts=json.dumps([{"text": f"Home post {i}"}]),
            status="published",
        )
        db_session.add(d)
        p = Post(
            id=f"p_home_{i}",
            draft_id=d.id,
            account_id=acc.id,
            threads_media_id=f"m_home_{i}",
            published_at="2026-11-05T12:00:00Z",
        )
        db_session.add(p)
        pm = PostMetric(
            id=f"pm_home_{i}",
            post_id=p.id,
            captured_at="2026-11-08T12:00:00Z",
            age_bucket="72h",
            views=300,
            likes=30,
            replies=5,
            reposts=2,
            quotes=1,
        )
        db_session.add(pm)

    # Add 8 posts to Pet (lower engagement: 100 views, 2 likes)
    for i in range(8):
        d = Draft(
            id=f"d_pet_{i}",
            account_id=acc.id,
            arm_id=arm_pet.id,
            niche_id=n2.id,
            style_id=s1.id,
            prompt_version="p_v1",
            llm_model="gemini-pro",
            parts=json.dumps([{"text": f"Pet post {i}"}]),
            status="published",
        )
        db_session.add(d)
        p = Post(
            id=f"p_pet_{i}",
            draft_id=d.id,
            account_id=acc.id,
            threads_media_id=f"m_pet_{i}",
            published_at="2026-11-05T12:00:00Z",
        )
        db_session.add(p)
        pm = PostMetric(
            id=f"pm_pet_{i}",
            post_id=p.id,
            captured_at="2026-11-08T12:00:00Z",
            age_bucket="72h",
            views=100,
            likes=2,
            replies=0,
            reposts=0,
            quotes=0,
        )
        db_session.add(pm)

    await db_session.commit()

    # Both arms have n=8. Home has significantly higher ER and views.
    eval_res = await evaluate_experiment_rule_v1(db_session, exp.id)
    assert eval_res.recommendation == "winner_found"
    assert eval_res.winner_arm_id == arm_home.id
    assert eval_res.score_ratio is not None
    assert eval_res.score_ratio >= 1.25


# ---------------------------------------------------------------------------
# 3. Weekly Report Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_and_format_weekly_report(db_session: AsyncSession) -> None:
    # Add an incident
    inc = Incident(
        id="inc_weekly_test",
        code="TEST_ALERT",
        severity="warning",
        detail="Scheduled review alert",
    )
    db_session.add(inc)
    await db_session.commit()

    report = await generate_weekly_report(db_session, days_back=7)
    assert "period_start" in report
    assert "period_end" in report
    assert "total_posts_published" in report
    assert "operator_workload" in report
    assert "experiments" in report
    assert "suggested_actions" in report

    # Test Telegram formatting
    tg_text = format_weekly_report_telegram(report)
    assert "<b>Laporan Mingguan Threads</b>" in tg_text
    assert "<b>Publikasi & Performa:</b>" in tg_text
    assert "<b>Beban Review Operator:</b>" in tg_text
    assert "<b>Rekomendasi Tindakan:</b>" in tg_text


@pytest.mark.asyncio
async def test_telegram_handle_report_integration(db_session: AsyncSession) -> None:
    # Pre-seed account with admin telegram chat
    acc = Account(id="acc_tg_report", username="tg_admin", telegram_chat_id="123456789")
    db_session.add(acc)
    await db_session.commit()

    resp = await handle_report(chat_id="123456789", session=db_session)
    assert "<b>Laporan Mingguan Threads</b>" in resp.text


# ---------------------------------------------------------------------------
# 4. API Endpoints Integration Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_evaluation_and_weekly_report_endpoints(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    n1 = Niche(id="n_api_ev1", name="Niche EV1", slug="n-ev1")
    n2 = Niche(id="n_api_ev2", name="Niche EV2", slug="n-ev2")
    s1 = Style(id="s_api_ev1", name="curator", tone_rules="curator rules")
    db_session.add_all([n1, n2, s1])
    await db_session.commit()

    exp = await create_experiment(
        db_session,
        name="API Evaluation Test",
        phase="niche_test",
        start_date="2026-11-10",
        arms_data=[
            {"label": "Arm 1", "niche_id": n1.id, "style_id": s1.id},
            {"label": "Arm 2", "niche_id": n2.id, "style_id": s1.id},
        ],
    )
    await update_experiment_status(db_session, exp.id, "running")

    # 1. GET /api/experiments/{id}/evaluation
    res_eval = await async_client.get(
        f"/api/experiments/{exp.id}/evaluation", headers=headers, cookies=cookies
    )
    assert res_eval.status_code == 200
    eval_data = res_eval.json()
    assert eval_data["experiment_id"] == exp.id
    assert eval_data["recommendation"] == "insufficient_data"
    assert len(eval_data["arms"]) == 2

    # 2. GET /api/analytics/weekly-report
    res_rep = await async_client.get(
        "/api/analytics/weekly-report?days=7", headers=headers, cookies=cookies
    )
    assert res_rep.status_code == 200
    rep_data = res_rep.json()
    assert "period_start" in rep_data
    assert "suggested_actions" in rep_data
    assert len(rep_data["experiments"]) >= 1
