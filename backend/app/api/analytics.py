"""app/api/analytics.py — Analytics, Post Metrics, Account Growth, and Benable Clicks endpoints (T-040 & T-041).

Safety & Compliance Principles:
1. Idempotent metrics storage: Bucketed measurements (1h, 24h, 72h, 7d).
2. Fail-soft collection: Missing media or API glitches do not halt the process.
3. Click attribution caveat: Benable clicks are product-and-period level, not individual post level.
4. Row-by-row CSV validation with clear error feedback.
5. All mutations require admin session + CSRF token, and append an audit log entry.
"""

from __future__ import annotations

import json
from typing import Any
from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.analytics.click_importer import (
    CLICK_ATTRIBUTION_CAVEAT,
    parse_and_import_clicks_csv,
    parse_date_str,
)
from app.analytics.metrics_collector import capture_account_snapshot, collect_post_metrics
from app.core.audit import record_audit_log
from app.core.security import get_current_admin, require_csrf
from app.db.models import Account, AccountSnapshot, Draft, LinkClick, Post, PostMetric, Product, utc_now_iso
from app.db.session import get_db
from app.experiments.weekly_report import generate_weekly_report
from app.schemas.analytics import (
    AccountSnapshotItem,
    AnalyticsOverviewResponse,
    ClickImportResponse,
    ClickImportRowError,
    CollectMetricsResponse,
    LinkClickCreate,
    LinkClickItem,
    LinkClickListResponse,
    PostMetricItem,
    PublishedPostAnalytics,
    WeeklyReportResponse,
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


# ---------------------------------------------------------------------------
# Link Clicks & Benable Import Endpoints (T-041)
# ---------------------------------------------------------------------------

@router.get("/clicks", response_model=LinkClickListResponse)
async def list_link_clicks(
    product_id: str | None = Query(default=None, description="Filter by product ID"),
    post_id: str | None = Query(default=None, description="Filter by post ID"),
    start_date: str | None = Query(default=None, description="Filter period >= start_date"),
    end_date: str | None = Query(default=None, description="Filter period <= end_date"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> LinkClickListResponse:
    """List recorded Benable link clicks with optional filtering and mandatory caveat notice."""
    stmt = (
        select(LinkClick)
        .options(selectinload(LinkClick.product))
        .order_by(LinkClick.period_start.desc(), LinkClick.created_at.desc())
    )

    if product_id:
        stmt = stmt.where(LinkClick.product_id == product_id)
    if post_id:
        stmt = stmt.where(LinkClick.post_id == post_id)
    if start_date:
        stmt = stmt.where(LinkClick.period_start >= start_date)
    if end_date:
        stmt = stmt.where(LinkClick.period_end <= end_date)

    res = await session.execute(stmt)
    all_items = res.scalars().all()

    total_clicks = sum(item.clicks for item in all_items)
    paginated_items = all_items[offset : offset + limit]

    items = [
        LinkClickItem(
            id=c.id,
            product_id=c.product_id,
            product_title=c.product.title if c.product else None,
            post_id=c.post_id,
            period_start=c.period_start,
            period_end=c.period_end,
            clicks=c.clicks,
            source=c.source,
            note=c.note,
            created_at=c.created_at,
        )
        for c in paginated_items
    ]

    return LinkClickListResponse(
        total_clicks=total_clicks,
        items_count=len(all_items),
        attribution_caveat=CLICK_ATTRIBUTION_CAVEAT,
        items=items,
    )


@router.post("/clicks", response_model=LinkClickItem, status_code=status.HTTP_201_CREATED)
async def create_link_click_manual(
    payload: LinkClickCreate,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> LinkClickItem:
    """Manually record a Benable link click entry."""
    # 1. Validate dates
    dt_start = parse_date_str(payload.period_start)
    dt_end = parse_date_str(payload.period_end)
    if not dt_start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid period_start date format: {payload.period_start}",
        )
    if not dt_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid period_end date format: {payload.period_end}",
        )
    if dt_start > dt_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="period_start cannot be after period_end",
        )

    # 2. Validate product / post existence
    product_title = None
    if payload.product_id:
        prod_res = await session.execute(select(Product).where(Product.id == payload.product_id))
        prod = prod_res.scalar_one_or_none()
        if not prod:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with id '{payload.product_id}' not found",
            )
        product_title = prod.title

    if payload.post_id:
        post_res = await session.execute(select(Post).where(Post.id == payload.post_id))
        if not post_res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Post with id '{payload.post_id}' not found",
            )

    if not payload.product_id and not payload.post_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least product_id or post_id must be provided",
        )

    click_entry = LinkClick(
        product_id=payload.product_id,
        post_id=payload.post_id,
        period_start=dt_start.isoformat(),
        period_end=dt_end.isoformat(),
        clicks=payload.clicks,
        source=payload.source or "benable_manual",
        note=payload.note,
    )
    session.add(click_entry)
    await session.commit()
    await session.refresh(click_entry)

    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="record_click",
        entity="link_clicks",
        entity_id=click_entry.id,
        detail={
            "product_id": click_entry.product_id,
            "post_id": click_entry.post_id,
            "clicks": click_entry.clicks,
            "period_start": click_entry.period_start,
            "period_end": click_entry.period_end,
        },
    )

    return LinkClickItem(
        id=click_entry.id,
        product_id=click_entry.product_id,
        product_title=product_title,
        post_id=click_entry.post_id,
        period_start=click_entry.period_start,
        period_end=click_entry.period_end,
        clicks=click_entry.clicks,
        source=click_entry.source,
        note=click_entry.note,
        created_at=click_entry.created_at,
    )


@router.post("/clicks/preview-csv", response_model=ClickImportResponse)
async def preview_clicks_csv(
    file: UploadFile | None = File(default=None),
    csv_content: str | None = Body(default=None, embed=True),
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> ClickImportResponse:
    """Dry-run preview of CSV Benable click import with row-by-row validation."""
    raw_text = ""
    if file:
        content_bytes = await file.read()
        try:
            raw_text = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raw_text = content_bytes.decode("latin-1")
    elif csv_content:
        raw_text = csv_content
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either a CSV file or csv_content text must be provided.",
        )

    res = await parse_and_import_clicks_csv(raw_text, session, dry_run=True)
    return ClickImportResponse(**res)


@router.post("/clicks/import-csv", response_model=ClickImportResponse)
async def import_clicks_csv(
    file: UploadFile | None = File(default=None),
    csv_content: str | None = Body(default=None, embed=True),
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> ClickImportResponse:
    """Import Benable clicks from CSV with row-by-row validation."""
    raw_text = ""
    if file:
        content_bytes = await file.read()
        try:
            raw_text = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raw_text = content_bytes.decode("latin-1")
    elif csv_content:
        raw_text = csv_content
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either a CSV file or csv_content text must be provided.",
        )

    res = await parse_and_import_clicks_csv(raw_text, session, dry_run=False)

    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="import_clicks_csv",
        entity="link_clicks",
        detail={
            "total_rows": res["total_rows"],
            "imported_count": res["imported_count"],
            "failed_count": res["failed_count"],
        },
    )

    return ClickImportResponse(**res)


@router.delete("/clicks/{click_id}")
async def delete_link_click(
    click_id: str,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> dict[str, Any]:
    """Delete a recorded link click entry."""
    res = await session.execute(select(LinkClick).where(LinkClick.id == click_id))
    item = res.scalar_one_or_none()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LinkClick with id '{click_id}' not found",
        )

    await session.delete(item)
    await session.commit()

    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="delete_click",
        entity="link_clicks",
        entity_id=click_id,
        detail={"product_id": item.product_id, "clicks": item.clicks},
    )

    return {"deleted": True, "id": click_id}


@router.get("/weekly-report", response_model=WeeklyReportResponse)
async def get_weekly_performance_report(
    days: int = Query(default=7, ge=1, le=30, description="Report window in days"),
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> WeeklyReportResponse:
    """Retrieve full weekly performance summary and rule_v1 experiment recommendations."""
    report = await generate_weekly_report(session, days_back=days)
    return WeeklyReportResponse(**report)

