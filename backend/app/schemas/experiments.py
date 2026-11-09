"""app/schemas/experiments.py — Pydantic schemas for Experiments, Arms, and Allocation (T-042)."""

from __future__ import annotations

import json
from typing import Any
from pydantic import BaseModel, Field


class ExperimentArmCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=100)
    target_posts: int = Field(default=12, ge=1, le=100, description="Target post count for this arm")
    niche_id: str | None = None
    style_id: str | None = None


class ExperimentArmResponse(BaseModel):
    id: str
    experiment_id: str
    label: str
    target_posts: int
    niche_id: str | None = None
    niche_name: str | None = None
    style_id: str | None = None
    style_name: str | None = None


class ExperimentCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=150)
    phase: str = Field(..., description="Phase: 'niche_test', 'style_test', or 'scale'")
    start_date: str = Field(..., description="Start date (YYYY-MM-DD or ISO)")
    end_date: str | None = None
    config: dict[str, Any] = Field(default_factory=dict, description="Experiment configuration options")
    arms: list[ExperimentArmCreate] = Field(..., min_length=2, description="At least 2 arms required")


class ExperimentUpdate(BaseModel):
    name: str | None = None
    status: str | None = None  # planned, running, completed, aborted
    end_date: str | None = None
    config: dict[str, Any] | None = None


class ArmProgressItem(BaseModel):
    arm_id: str
    label: str
    niche_id: str | None = None
    niche_name: str | None = None
    style_id: str | None = None
    style_name: str | None = None
    target_posts: int
    total_drafts: int
    published_posts: int
    metrics_completed_72h: int
    progress_pct: float


class ExperimentResponse(BaseModel):
    id: str
    name: str
    phase: str
    status: str
    start_date: str
    end_date: str | None = None
    config: dict[str, Any]
    created_at: str
    updated_at: str
    arms: list[ExperimentArmResponse] = Field(default_factory=list)


class ExperimentProgressResponse(BaseModel):
    experiment_id: str
    name: str
    phase: str
    status: str
    total_target_posts: int
    total_published_posts: int
    overall_progress_pct: float
    arms: list[ArmProgressItem] = Field(default_factory=list)


class AllocateNextArmResponse(BaseModel):
    experiment_id: str
    has_eligible_arm: bool
    recommended_arm: ExperimentArmResponse | None = None
    reason: str
