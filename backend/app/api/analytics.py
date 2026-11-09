"""app/api/analytics.py — Analytics, Post Metrics, and Account Growth endpoints (T-040).

Follows strict safety principles:
1. Idempotent metrics storage: Bucketed measurements (1h, 24h, 72h, 7d).
2. Fail-soft collection: Missing media or API glitches do not halt the process.
3. Manual trigger capability with audit trail tracking.
"""

from __future__ import annotations

import json
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.analytics.metrics_collector import capture_account_snapshot, collect_post_metrics
from app.core.audit import record_audit_log
from app.core.security import get_current_admin, require_csrf
from app.db.models import Account, AccountSnapshot, Draft, Post, PostMetric
from app.db.session import get_db
from app.schemas.analytics import (
    AccountSnapshotItem,
    AnalyticsOverviewResponse,
    CollectMetricsResponse,
    PostMetricItem,
    PublishedPostAnalytics,
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _extract_text_snippet(draft: Draft | None) -> str:
    if not draft or not draft.parts:
        return "Postingan Threads"
    try:
        parts = json.loads(draft.parts)
        if parts and isinstance(parts, list) and "text" in parts[0]:
            t = parts[0]["text"]
            return t[:100] + ("..." if len(t) > 100 else "")
    except Exception:
        pass
    return "Postingan Threads"


@router.get("/overview", response_model=AnalyticsOverviewResponse)
async def get_analytics_overview(
    limit_recent: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> AnalyticsOverviewResponse:
    """Retrieve aggregated performance metrics and recent post analytics."""
    posts_q = (
        select(Post)
        .options(
            selectinload(Post.metrics),
            selectinload(Post.draft).selectinload(Draft.niche),
            selectinload(Post.draft).selectinload(Draft.style),
            selectinload(Post.draft).selectinload(Draft.product),
        )
        .order_by(Post.created_at.desc())
    )
    res = await session.execute(posts_q)
    all_posts = res.scalars().all()

    total_posts = len(all_posts)
    total_views = 0
    total_likes = 0
    total_replies = 0
    total_reposts = 0
    total_quotes = 0

    bucket_totals: dict[str, dict[str, int]] = {
        "1h": {"views": 0, "likes": 0, "replies": 0, "reposts": 0},
        "24h": {"views": 0, "likes": 0, "replies": 0, "reposts": 0},
        "72h": {"views": 0, "likes": 0, "replies": 0, "reposts": 0},
        "7d": {"views": 0, "likes": 0, "replies": 0, "reposts": 0},
    }

    recent_post_items: list[PublishedPostAnalytics] = []

    for idx, p in enumerate(all_posts):
        # Find latest metric values
        latest_v = 0
        latest_l = 0
        latest_rep = 0
        latest_rp = 0

        metric_items: list[PostMetricItem] = []
        for m in sorted(p.metrics, key=lambda x: x.captured_at):
            v = m.views or 0
            l = m.likes or 0
            rep = m.replies or 0
            rp = m.reposts or 0
            q = m.quotes or 0

            latest_v = max(latest_v, v)
            latest_l = max(latest_l, l)
            latest_rep = max(latest_rep, rep)
            latest_rp = max(latest_rp, rp)

            if m.age_bucket in bucket_totals:
                bucket_totals[m.age_bucket]["views"] += v
                bucket_totals[m.age_bucket]["likes"] += l
                bucket_totals[m.age_bucket]["replies"] += rep
                bucket_totals[m.age_bucket]["reposts"] += rp

            metric_items.append(
                PostMetricItem(
                    id=m.id,
                    age_bucket=m.age_bucket,
                    captured_at=m.captured_at,
                    views=v,
                    likes=l,
                    replies=rep,
                    reposts=rp,
                    quotes=q,
                )
            )

        total_views += latest_v
        total_likes += latest_l
        total_replies += latest_rep
        total_reposts += latest_rp

        if idx < limit_recent:
            draft = p.draft
            recent_post_items.append(
                PublishedPostAnalytics(
                    post_id=p.id,
                    draft_id=p.draft_id,
                    threads_media_id=p.threads_media_id,
                    permalink=p.permalink,
                    published_at=p.published_at or p.created_at,
                    text_snippet=_extract_text_snippet(draft),
                    niche_name=draft.niche.name if draft and draft.niche else None,
                    style_name=draft.style.name if draft and draft.style else None,
                    product_title=draft.product.title if draft and draft.product else None,
                    latest_views=latest_v,
                    latest_likes=latest_l,
                    latest_replies=latest_rep,
                    latest_reposts=latest_rp,
                    metrics=metric_items,
                )
            )

    return AnalyticsOverviewResponse(
        total_posts_published=total_posts,
        total_views=total_views,
        total_likes=total_likes,
        total_replies=total_replies,
        total_reposts=total_reposts,
        total_quotes=total_quotes,
        bucket_totals=bucket_totals,
        recent_posts=recent_post_items,
    )


@router.get("/account-growth", response_model=list[AccountSnapshotItem])
async def get_account_growth(
    limit: int = Query(default=30, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> list[AccountSnapshotItem]:
    """Retrieve historical account follower and profile view growth."""
    q = select(AccountSnapshot).order_by(AccountSnapshot.captured_at.asc()).limit(limit)
    res = await session.execute(q)
    snapshots = res.scalars().all()
    return [
        AccountSnapshotItem(
            id=s.id,
            captured_at=s.captured_at,
            followers=s.followers,
            profile_views=s.profile_views,
        )
        for s in snapshots
    ]


@router.post("/collect-now", response_model=CollectMetricsResponse)
async def trigger_collect_metrics_manual(
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> CollectMetricsResponse:
    """Manually trigger metrics collection loop for all due post age buckets."""
    result = await collect_post_metrics(session)
    snapshot = await capture_account_snapshot(session)

    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="collect_metrics_manual",
        entity="analytics",
        detail={
            "metrics_saved": result.metrics_saved,
            "posts_failed": result.posts_failed,
            "posts_evaluated": result.posts_evaluated,
            "snapshot_id": snapshot.id,
        },
    )

    return CollectMetricsResponse(
        success=True,
        posts_evaluated=result.posts_evaluated,
        metrics_saved=result.metrics_saved,
        posts_failed=result.posts_failed,
        buckets_processed=result.buckets_processed,
        snapshot_id=snapshot.id,
    )
