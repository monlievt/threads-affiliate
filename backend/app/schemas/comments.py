"""app/schemas/comments.py — Pydantic schemas for Value-First Comments (Feature 10).

Follows strict safety principles:
1. Always manual review: Comments are never automatically posted without human oversight.
2. Daily limits: Enforces warmup tier max replies and hard ceiling HARD_MAX_REPLIES_PER_DAY.
3. Link warning: Value-first priority, prominent warnings when link is present.
4. Avoid list transparency: Displays prohibited spam/hype patterns.
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class CommentOption(BaseModel):
    option_id: str
    strategy: Literal["insight", "relate", "question", "curator_tip"]
    strategy_label: str
    text: str
    char_count: int
    has_link: bool
    link_url: str | None = None
    safety_valid: bool
    safety_issues: list[str] = Field(default_factory=list)


class CommentGenerateRequest(BaseModel):
    target_post_url: str = Field(..., description="Threads target post URL e.g. https://www.threads.net/@user/post/...")
    target_post_text: str = Field(..., min_length=5, description="Snippet or content of the target post being replied to.")
    strategy: Literal["all", "insight", "relate", "question"] = "all"
    niche_id: str | None = None
    persona_id: str | None = None
    include_link: bool = Field(default=False, description="Default FALSE. Keep comments value-first without links.")
    product_id: str | None = None


class CommentGenerateResponse(BaseModel):
    target_post_url: str
    target_post_id: str | None = None
    options: list[CommentOption]
    daily_replies_used: int
    daily_replies_limit: int
    hard_max_replies: int
    remaining_replies_today: int
    avoid_list: list[str]


class CommentPublishRequest(BaseModel):
    target_post_url: str
    selected_text: str = Field(..., min_length=2)
    link_url: str | None = None
    action_type: Literal["publish_api", "copied_clipboard"] = "copied_clipboard"


class CommentPublishResponse(BaseModel):
    success: bool
    message: str
    action_type: str
    threads_reply_id: str | None = None
    daily_replies_used: int
    remaining_replies_today: int


class CommentsQuotaResponse(BaseModel):
    replies_today: int
    max_replies_today: int
    hard_max_replies: int
    remaining_today: int
    is_quota_full: bool
    avoid_list: list[str]
