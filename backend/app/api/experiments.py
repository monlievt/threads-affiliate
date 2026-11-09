"""app/api/experiments.py — Experiment and Arm Management endpoints (T-042).

Safety & Experimentation Principles:
1. Enforces single-variable testing (niche_test vs style_test).
2. Manages state machine transitions with single-running experiment per phase limit.
3. Allocates arms evenly and alternates to avoid same-niche streaks.
4. Requires admin auth and CSRF token on all state mutations, with full audit logging.
"""

from __future__ import annotations

import json
from typing import Any
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import record_audit_log
from app.core.security import get_current_admin, require_csrf
from app.db.models import Experiment, ExperimentArm
from app.db.session import get_db
from app.experiments.allocator import select_next_arm_for_generation
from app.experiments.rule_v1 import evaluate_experiment_rule_v1
from app.experiments.service import (
    create_experiment,
    get_experiment_progress,
    update_experiment_status,
)
from app.schemas.experiments import (
    AllocateNextArmResponse,
    ArmRuleEvaluationResponse,
    ExperimentArmResponse,
    ExperimentCreate,
    ExperimentEvaluationResponse,
    ExperimentProgressResponse,
    ExperimentResponse,
    ExperimentUpdate,
)

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


def _format_experiment_response(exp: Experiment) -> ExperimentResponse:
    arms_resp = []
    for a in exp.arms or []:
        arms_resp.append(
            ExperimentArmResponse(
                id=a.id,
                experiment_id=a.experiment_id,
                label=a.label,
                target_posts=a.target_posts,
                niche_id=a.niche_id,
                niche_name=a.niche.name if getattr(a, "niche", None) else None,
                style_id=a.style_id,
                style_name=a.style.name if getattr(a, "style", None) else None,
            )
        )

    try:
        cfg = json.loads(exp.config) if exp.config else {}
    except Exception:
        cfg = {}

    return ExperimentResponse(
        id=exp.id,
        name=exp.name,
        phase=exp.phase,
        status=exp.status,
        start_date=exp.start_date,
        end_date=exp.end_date,
        config=cfg,
        created_at=exp.created_at,
        updated_at=exp.updated_at,
        arms=arms_resp,
    )


@router.get("", response_model=list[ExperimentResponse])
async def list_experiments(
    phase: str | None = Query(default=None, description="Filter by phase"),
    status_filter: str | None = Query(default=None, alias="status", description="Filter by status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> list[ExperimentResponse]:
    """List experiments with optional filters."""
    stmt = (
        select(Experiment)
        .options(
            selectinload(Experiment.arms).selectinload(ExperimentArm.niche),
            selectinload(Experiment.arms).selectinload(ExperimentArm.style),
        )
        .order_by(Experiment.created_at.desc())
    )

    if phase:
        stmt = stmt.where(Experiment.phase == phase)
    if status_filter:
        stmt = stmt.where(Experiment.status == status_filter)

    stmt = stmt.offset(offset).limit(limit)
    res = await session.execute(stmt)
    experiments = res.scalars().all()

    return [_format_experiment_response(e) for e in experiments]


@router.post("", response_model=ExperimentResponse, status_code=status.HTTP_201_CREATED)
async def create_new_experiment(
    payload: ExperimentCreate,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> ExperimentResponse:
    """Create a new experiment with validated arms obeying single-variable rules."""
    arms_data = [a.model_dump() for a in payload.arms]
    try:
        exp = await create_experiment(
            session=session,
            name=payload.name,
            phase=payload.phase,
            start_date=payload.start_date,
            arms_data=arms_data,
            end_date=payload.end_date,
            config=payload.config,
            actor=admin.get("sub", "admin"),
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )

    # Re-query with eager loads
    res = await session.execute(
        select(Experiment)
        .options(
            selectinload(Experiment.arms).selectinload(ExperimentArm.niche),
            selectinload(Experiment.arms).selectinload(ExperimentArm.style),
        )
        .where(Experiment.id == exp.id)
    )
    loaded_exp = res.scalar_one()
    return _format_experiment_response(loaded_exp)


@router.get("/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment_details(
    experiment_id: str,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> ExperimentResponse:
    """Retrieve details of a single experiment."""
    res = await session.execute(
        select(Experiment)
        .options(
            selectinload(Experiment.arms).selectinload(ExperimentArm.niche),
            selectinload(Experiment.arms).selectinload(ExperimentArm.style),
        )
        .where(Experiment.id == experiment_id)
    )
    exp = res.scalar_one_or_none()
    if not exp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment '{experiment_id}' not found",
        )
    return _format_experiment_response(exp)


@router.patch("/{experiment_id}/status", response_model=ExperimentResponse)
async def change_experiment_status(
    experiment_id: str,
    status_update: str = Body(..., embed=True),
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> ExperimentResponse:
    """Transition experiment status (e.g. start experiment, mark completed)."""
    try:
        exp = await update_experiment_status(
            session=session,
            experiment_id=experiment_id,
            new_status=status_update,
            actor=admin.get("sub", "admin"),
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )

    res = await session.execute(
        select(Experiment)
        .options(
            selectinload(Experiment.arms).selectinload(ExperimentArm.niche),
            selectinload(Experiment.arms).selectinload(ExperimentArm.style),
        )
        .where(Experiment.id == exp.id)
    )
    loaded_exp = res.scalar_one()
    return _format_experiment_response(loaded_exp)


@router.get("/{experiment_id}/progress", response_model=ExperimentProgressResponse)
async def get_progress(
    experiment_id: str,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> ExperimentProgressResponse:
    """Get real-time publication and metric progress across arms."""
    try:
        progress_data = await get_experiment_progress(session, experiment_id)
        return ExperimentProgressResponse(**progress_data)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.post("/{experiment_id}/allocate-next", response_model=AllocateNextArmResponse)
async def allocate_next_arm(
    experiment_id: str,
    last_arm_id: str | None = Body(default=None, embed=True),
    last_niche_id: str | None = Body(default=None, embed=True),
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> AllocateNextArmResponse:
    """Calculate and recommend the next arm for balanced content generation."""
    arm, reason = await select_next_arm_for_generation(
        session=session,
        experiment_id=experiment_id,
        last_arm_id=last_arm_id,
        last_niche_id=last_niche_id,
    )

    arm_resp = None
    if arm:
        arm_resp = ExperimentArmResponse(
            id=arm.id,
            experiment_id=arm.experiment_id,
            label=arm.label,
            target_posts=arm.target_posts,
            niche_id=arm.niche_id,
            niche_name=arm.niche.name if getattr(arm, "niche", None) else None,
            style_id=arm.style_id,
            style_name=arm.style.name if getattr(arm, "style", None) else None,
        )

    return AllocateNextArmResponse(
        experiment_id=experiment_id,
        has_eligible_arm=arm is not None,
        recommended_arm=arm_resp,
        reason=reason,
    )


@router.get("/{experiment_id}/evaluation", response_model=ExperimentEvaluationResponse)
async def get_experiment_evaluation(
    experiment_id: str,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> ExperimentEvaluationResponse:
    """Evaluate experiment using rule_v1 decision logic (docs/07 §3)."""
    try:
        eval_result = await evaluate_experiment_rule_v1(session, experiment_id)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )

    arms_resp = [
        ArmRuleEvaluationResponse(
            arm_id=a.arm_id,
            label=a.label,
            niche_id=a.niche_id,
            niche_name=a.niche_name,
            style_id=a.style_id,
            style_name=a.style_name,
            n=a.n,
            insufficient_data=a.insufficient_data,
            median_views_72=a.median_views_72,
            median_er_72=a.median_er_72,
            click_rate=a.click_rate,
            raw_clicks=a.raw_clicks,
            score=a.score,
            rank=a.rank,
            outliers_views=a.outliers_views,
            outliers_er=a.outliers_er,
        )
        for a in eval_result.arms
    ]

    return ExperimentEvaluationResponse(
        experiment_id=eval_result.experiment_id,
        phase=eval_result.phase,
        status=eval_result.status,
        evaluated_at=eval_result.evaluated_at,
        total_arms=eval_result.total_arms,
        eligible_arms_count=eval_result.eligible_arms_count,
        recommendation=eval_result.recommendation,
        winner_arm_id=eval_result.winner_arm_id,
        winner_arm_label=eval_result.winner_arm_label,
        runner_up_arm_id=eval_result.runner_up_arm_id,
        score_ratio=eval_result.score_ratio,
        recommended_extension_posts=eval_result.recommended_extension_posts,
        explanation=eval_result.explanation,
        arms=arms_resp,
    )


