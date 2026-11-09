"""app/schemas/settings.py — Pydantic schemas for System Settings, Full Auto Eligibility, Incidents, and Audit Trail.

Enforces:
1. Operational limits clamped by hard config limits.
2. Full auto eligibility validation rules.
3. Incident tracking and resolution schemas.
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class FullAutoCriterion(BaseModel):
    required: Any
    current: Any
    passed: bool
    label: str


class FullAutoEligibilityResponse(BaseModel):
    eligible: bool
    summary_reason: str
    criteria: dict[str, FullAutoCriterion]


class AccountSettingsResponse(BaseModel):
    id: str
    username: str | None = None
    threads_user_id: str | None = None
    country_code: str
    timezone: str
    active_hours_start: int
    active_hours_end: int
    automation_mode: Literal["manual_approve", "auto_sampled", "full_auto"]
    sample_review_pct: int
    warmup_started_at: str | None = None
    warmup_age_days: int
    token_valid: bool
    token_expires_at: str | None = None
    days_until_token_expiry: int | None = None
    hard_max_posts_per_day: int
    hard_max_replies_per_day: int


class AccountSettingsUpdate(BaseModel):
    active_hours_start: int | None = Field(default=None, ge=0, le=23)
    active_hours_end: int | None = Field(default=None, ge=1, le=24)
    automation_mode: Literal["manual_approve", "auto_sampled", "full_auto"] | None = None
    sample_review_pct: int | None = Field(default=None, ge=10, le=100)
    timezone: str | None = None


class IncidentResponse(BaseModel):
    id: str
    severity: Literal["info", "warning", "critical"]
    code: str
    detail: str | None = None
    resolved_at: str | None = None
    created_at: str


class IncidentResolveRequest(BaseModel):
    resolution_notes: str = Field(..., min_length=3, description="Notes on how the incident was investigated and resolved.")


class AuditLogResponse(BaseModel):
    id: str
    at: str
    actor: str
    action: str
    entity: str | None = None
    entity_id: str | None = None
    detail: str | None = None
