"""app/schemas/analytics.py — Pydantic schemas for Metrics and Analytics endpoints."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class PostMetricItem(BaseModel):
    id: str
    age_bucket: str
    captured_at: str
    views: int = 0
    likes: int = 0
    replies: int = 0
    reposts: int = 0
    quotes: int = 0


class PublishedPostAnalytics(BaseModel):
    post_id: str
    draft_id: str
    threads_media_id: str | None = None
    permalink: str | None = None
    published_at: str
    text_snippet: str
    niche_name: str | None = None
    style_name: str | None = None
    product_title: str | None = None
    latest_views: int = 0
    latest_likes: int = 0
    latest_replies: int = 0
    latest_reposts: int = 0
    metrics: list[PostMetricItem] = Field(default_factory=list)


class AnalyticsOverviewResponse(BaseModel):
    total_posts_published: int
    total_views: int
    total_likes: int
    total_replies: int
    total_reposts: int
    total_quotes: int
    bucket_totals: dict[str, dict[str, int]]
    recent_posts: list[PublishedPostAnalytics] = Field(default_factory=list)


class AccountSnapshotItem(BaseModel):
    id: str
    captured_at: str
    followers: int | None = None
    profile_views: int | None = None


class CollectMetricsResponse(BaseModel):
    success: bool
    posts_evaluated: int
    metrics_saved: int
    posts_failed: int
    buckets_processed: dict[str, int]
    snapshot_id: str | None = None
