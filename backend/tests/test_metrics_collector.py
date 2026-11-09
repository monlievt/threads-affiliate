"""tests/test_metrics_collector.py — Test suite for Metrics Collector and Analytics API (T-040).

Verifies:
1. Bucket eligibility logic for 1h, 24h, 72h, and 7d thresholds.
2. Idempotent collection: Re-runs do not create duplicate records.
3. Fail-soft architecture: Post failures (e.g. API error or missing media) do not halt collection of other posts.
4. Account snapshot recording for followers and profile views growth.
5. GET /api/analytics/overview, GET /api/analytics/account-growth, and POST /api/analytics/collect-now.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.metrics_collector import (
    capture_account_snapshot,
    collect_post_metrics,
    determine_pending_buckets,
)
from app.core.clock import utc_now, utc_now_iso
from app.core.security import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, create_session_token
from app.db.models import Account, AccountSnapshot, Draft, Post, PostMetric
from app.threads.fake import FakeThreadsClient


def _get_auth_headers_and_cookies() -> tuple[dict[str, str], dict[str, str]]:
    token, csrf_token = create_session_token("admin")
    headers = {"X-CSRF-Token": csrf_token}
    cookies = {
        SESSION_COOKIE_NAME: token,
        CSRF_COOKIE_NAME: csrf_token,
    }
    return headers, cookies


def test_determine_pending_buckets_logic() -> None:
    now = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Post published 30 mins ago -> 0 buckets
    pub_30m = (now - timedelta(minutes=30)).isoformat()
    assert determine_pending_buckets(pub_30m, set(), now) == []

    # 2. Post published 2 hours ago -> ["1h"]
    pub_2h = (now - timedelta(hours=2)).isoformat()
    assert determine_pending_buckets(pub_2h, set(), now) == ["1h"]

    # If 1h already collected -> 0 buckets
    assert determine_pending_buckets(pub_2h, {"1h"}, now) == []

    # 3. Post published 30 hours ago -> ["1h", "24h"]
    pub_30h = (now - timedelta(hours=30)).isoformat()
    assert determine_pending_buckets(pub_30h, set(), now) == ["1h", "24h"]
    assert determine_pending_buckets(pub_30h, {"1h"}, now) == ["24h"]

    # 4. Post published 80 hours ago -> ["1h", "24h", "72h"]
    pub_80h = (now - timedelta(hours=80)).isoformat()
    assert determine_pending_buckets(pub_80h, {"1h", "24h"}, now) == ["72h"]

    # 5. Post published 8 days (192 hours) ago -> all 4 buckets
    pub_8d = (now - timedelta(days=8)).isoformat()
    assert determine_pending_buckets(pub_8d, {"1h", "24h", "72h"}, now) == ["7d"]


@pytest.fixture
async def setup_metrics_environment(db_session: AsyncSession) -> dict[str, str]:
    now = utc_now()
    now_iso = now.isoformat()

    account = Account(
        id="acc_metrics_test",
        username="metrics_user",
        display_name="Metrics User",
        country_code="US",
        timezone="America/New_York",
        status="active",
        created_at=now_iso,
        updated_at=now_iso,
    )
    db_session.add(account)

    # Draft 1 + Post 1 (Published 2 hours ago -> eligible for 1h)
    d1 = Draft(
        id="draft_m1",
        account_id=account.id,
        kind="post",
        prompt_version="p_v1",
        llm_model="test",
        parts=json.dumps([{"text": "Post 1 text"}]),
        text_hash="hash_m1",
        status="published",
        created_at=now_iso,
        updated_at=now_iso,
    )
    p1 = Post(
        id="post_m1",
        draft_id=d1.id,
        account_id=account.id,
        threads_media_id="media_post_1",
        published_at=(now - timedelta(hours=2)).isoformat(),
        created_at=now_iso,
    )

    # Draft 2 + Post 2 (Published 30 hours ago -> eligible for 1h and 24h)
    d2 = Draft(
        id="draft_m2",
        account_id=account.id,
        kind="post",
        prompt_version="p_v1",
        llm_model="test",
        parts=json.dumps([{"text": "Post 2 text"}]),
        text_hash="hash_m2",
        status="published",
        created_at=now_iso,
        updated_at=now_iso,
    )
    p2 = Post(
        id="post_m2",
        draft_id=d2.id,
        account_id=account.id,
        threads_media_id="media_post_2",
        published_at=(now - timedelta(hours=30)).isoformat(),
        created_at=now_iso,
    )

    db_session.add_all([d1, p1, d2, p2])
    await db_session.commit()

    return {
        "account_id": account.id,
        "post_1_id": p1.id,
        "post_2_id": p2.id,
    }


@pytest.mark.asyncio
async def test_collect_post_metrics_idempotency(
    db_session: AsyncSession,
    setup_metrics_environment: dict[str, str],
) -> None:
    client = FakeThreadsClient()
    client.insights_data["media_post_1"] = {"views": 250, "likes": 20, "replies": 5, "reposts": 2, "quotes": 1}
    client.insights_data["media_post_2"] = {"views": 800, "likes": 65, "replies": 12, "reposts": 8, "quotes": 3}

    # Run 1: Should collect 1h for post 1, and 1h + 24h for post 2 (Total 3 metrics)
    res1 = await collect_post_metrics(db_session, client=client)
    assert res1.posts_evaluated >= 2
    assert res1.metrics_saved == 3
    assert res1.posts_failed == 0

    # Verify metrics in DB
    metrics_p1 = (
        await db_session.execute(select(PostMetric).where(PostMetric.post_id == setup_metrics_environment["post_1_id"]))
    ).scalars().all()
    assert len(metrics_p1) == 1
    assert metrics_p1[0].age_bucket == "1h"
    assert metrics_p1[0].views == 250

    metrics_p2 = (
        await db_session.execute(select(PostMetric).where(PostMetric.post_id == setup_metrics_environment["post_2_id"]))
    ).scalars().all()
    assert len(metrics_p2) == 2
    buckets_p2 = {m.age_bucket for m in metrics_p2}
    assert buckets_p2 == {"1h", "24h"}

    # Run 2: Immediately re-running should collect 0 new metrics (idempotent no-op)
    res2 = await collect_post_metrics(db_session, client=client)
    assert res2.metrics_saved == 0
    assert res2.posts_failed == 0


@pytest.mark.asyncio
async def test_collect_post_metrics_fail_soft(
    db_session: AsyncSession,
    setup_metrics_environment: dict[str, str],
) -> None:
    class FailingInsightsClient(FakeThreadsClient):
        async def get_insights(self, media_id: str) -> dict[str, int]:
            if media_id == "media_post_1":
                raise RuntimeError("Simulated API 500 or Media Not Found on Threads")
            return {"views": 100, "likes": 5, "replies": 1, "reposts": 0, "quotes": 0}

    client = FailingInsightsClient()

    # Post 1 fails, but post 2 should succeed without aborting the loop
    res = await collect_post_metrics(db_session, client=client)
    assert res.posts_failed == 1
    assert res.metrics_saved == 2  # post 2 got 1h and 24h successfully!


@pytest.mark.asyncio
async def test_account_snapshot_capture(
    db_session: AsyncSession,
    setup_metrics_environment: dict[str, str],
) -> None:
    snap = await capture_account_snapshot(
        db_session,
        account_id=setup_metrics_environment["account_id"],
        followers=320,
        profile_views=1400,
    )
    assert snap.id is not None
    assert snap.followers == 320
    assert snap.profile_views == 1400

    # Verify in DB
    db_snap = await db_session.get(AccountSnapshot, snap.id)
    assert db_snap is not None
    assert db_snap.followers == 320


@pytest.mark.asyncio
async def test_analytics_api_endpoints(
    client: AsyncClient,
    db_session: AsyncSession,
    setup_metrics_environment: dict[str, str],
) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    # Pre-populate metric and snapshot
    metric = PostMetric(
        post_id=setup_metrics_environment["post_1_id"],
        age_bucket="1h",
        views=300,
        likes=25,
        replies=4,
        reposts=2,
        quotes=1,
    )
    db_session.add(metric)
    await capture_account_snapshot(
        db_session,
        account_id=setup_metrics_environment["account_id"],
        followers=500,
        profile_views=2000,
    )
    await db_session.commit()

    # 1. GET /api/analytics/overview
    resp_overview = await client.get("/api/analytics/overview", headers=headers, cookies=cookies)
    assert resp_overview.status_code == 200
    data = resp_overview.json()
    assert data["total_posts_published"] >= 2
    assert data["total_views"] >= 300
    assert "1h" in data["bucket_totals"]
    assert len(data["recent_posts"]) >= 2

    # 2. GET /api/analytics/account-growth
    resp_growth = await client.get("/api/analytics/account-growth", headers=headers, cookies=cookies)
    assert resp_growth.status_code == 200
    growth_list = resp_growth.json()
    assert len(growth_list) >= 1
    assert growth_list[0]["followers"] == 500

    # 3. POST /api/analytics/collect-now
    resp_collect = await client.post("/api/analytics/collect-now", headers=headers, cookies=cookies)
    assert resp_collect.status_code == 200
    collect_data = resp_collect.json()
    assert collect_data["success"] is True
    assert collect_data["snapshot_id"] is not None
