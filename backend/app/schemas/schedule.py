"""app/schemas/schedule.py — Pydantic schemas for Calendar and Schedule Management.

Enforces:
1. Dual timezone representation: Target (America/New_York) and Operator (Asia/Jakarta).
2. Rate governor and active hours transparency.
3. Drag-and-drop / move-slot validation schemas.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class CalendarSlot(BaseModel):
    id: str
    draft_id: str
    status: str
    scheduled_at_utc: str
    scheduled_at_target: str = Field(..., description="E.g. '14:30 EST'")
    scheduled_at_operator: str = Field(..., description="E.g. '02:30 WIB'")
    hour_target: int = Field(..., description="Hour in target timezone (0-23)")
    minute_target: int = Field(..., description="Minute in target timezone (0-59)")
    text_snippet: str
    niche_name: str | None = None
    style_name: str | None = None
    product_title: str | None = None


class CalendarDay(BaseModel):
    date: str = Field(..., description="YYYY-MM-DD in target timezone")
    day_name: str = Field(..., description="E.g. Monday, Tuesday")
    is_today: bool
    scheduled_count: int
    published_count: int
    max_posts: int
    remaining_quota: int
    is_quota_full: bool
    slots: list[CalendarSlot] = Field(default_factory=list)


class GovernorRulesSummary(BaseModel):
    target_timezone: str = "America/New_York"
    operator_timezone: str = "Asia/Jakarta"
    active_hours_start: int = 9
    active_hours_end: int = 21
    active_hours_label: str = "09:00 - 21:00 EST"
    operator_active_hours_label: str = "21:00 - 09:00 (+1) WIB"
    min_interval_minutes: int = 180
    warmup_tier_label: str = "Week 1"
    max_posts_per_day: int = 2


class CalendarResponse(BaseModel):
    start_date: str
    end_date: str
    days: list[CalendarDay]
    governor: GovernorRulesSummary


class MoveSlotRequest(BaseModel):
    draft_id: str
    new_scheduled_at: str = Field(..., description="Target ISO UTC datetime string")


class MoveSlotResponse(BaseModel):
    success: bool
    draft_id: str
    new_scheduled_at_utc: str
    new_scheduled_at_target: str
    new_scheduled_at_operator: str
    status: str
    message: str


class ValidateSlotRequest(BaseModel):
    draft_id: str | None = None
    candidate_scheduled_at: str = Field(..., description="Candidate ISO UTC datetime string")


class ValidateSlotResponse(BaseModel):
    valid: bool
    reason: str | None = None
    target_time_formatted: str
    operator_time_formatted: str
    is_active_hours: bool
    violates_interval: bool = False
    violates_quota: bool = False
