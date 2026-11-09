"""app/experiments/service.py — Experiment lifecycle management and validation service (T-042).

Enforces safety & scientific experimentation rules (docs/07 §1 & §2):
1. Single variable test:
   - 'niche_test': Variable is niche; style must remain constant across all arms.
   - 'style_test': Variable is style; niche must remain constant across all arms.
2. Arms requirement: Minimum 2 arms per experiment; target_posts >= 1.
3. State machine transitions: planned -> running -> completed | aborted.
4. Concurrency rule: Only 1 active ('running') experiment allowed per phase at any time.
5. Audit trail on all lifecycle changes.
"""

from __future__ import annotations

import json
from typing import Any
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import record_audit_log
from app.core.clock import utc_now_iso
from app.db.models import Draft, Experiment, ExperimentArm, Niche, Post, PostMetric, Style


VALID_PHASES = {"niche_test", "style_test", "scale"}
VALID_STATUSES = {"planned", "running", "completed", "aborted"}


async def create_experiment(
    session: AsyncSession,
    name: str,
    phase: str,
    start_date: str,
    arms_data: list[dict[str, Any]],
    end_date: str | None = None,
    config: dict[str, Any] | None = None,
    actor: str = "admin",
) -> Experiment:
    """Create a new experiment with validated arms obeying scientific principles."""
    if phase not in VALID_PHASES:
        raise ValueError(f"Invalid phase '{phase}'. Must be one of: {VALID_PHASES}")

    if len(arms_data) < 2:
        raise ValueError("An experiment requires at least 2 comparison arms.")

    config = config or {}

    # Validate arm properties
    niche_ids: list[str] = []
    style_ids: list[str] = []

    for idx, arm in enumerate(arms_data, start=1):
        target = arm.get("target_posts", 12)
        if target < 1:
            raise ValueError(f"Arm {idx} target_posts must be >= 1.")
        n_id = arm.get("niche_id")
        s_id = arm.get("style_id")
        if n_id:
            niche_ids.append(n_id)
        if s_id:
            style_ids.append(s_id)

    # 1. Enforce single-variable testing principle (docs/07 §1)
    if phase == "niche_test":
        # Niches must be distinct
        if len(set(niche_ids)) != len(arms_data):
            raise ValueError("In 'niche_test', each arm must test a distinct niche.")
        # Style must be constant across arms if specified
        if style_ids and len(set(style_ids)) > 1:
            raise ValueError("In 'niche_test', the style must remain constant across all arms (single variable rule).")

    elif phase == "style_test":
        # Styles must be distinct
        if len(set(style_ids)) != len(arms_data):
            raise ValueError("In 'style_test', each arm must test a distinct style.")
        # Niche must be constant across arms if specified
        if niche_ids and len(set(niche_ids)) > 1:
            raise ValueError("In 'style_test', the niche must remain constant across all arms (single variable rule).")

    # 2. Verify existence of referenced niches and styles
    if niche_ids:
        niches_q = await session.execute(select(Niche.id).where(Niche.id.in_(niche_ids)))
        found_niches = set(niches_q.scalars().all())
        missing_n = set(niche_ids) - found_niches
        if missing_n:
            raise ValueError(f"Referenced niche(s) not found: {missing_n}")

    if style_ids:
        styles_q = await session.execute(select(Style.id).where(Style.id.in_(style_ids)))
        found_styles = set(styles_q.scalars().all())
        missing_s = set(style_ids) - found_styles
        if missing_s:
            raise ValueError(f"Referenced style(s) not found: {missing_s}")

    experiment = Experiment(
        name=name.strip(),
        phase=phase,
        start_date=start_date.strip(),
        end_date=end_date.strip() if end_date else None,
        config=json.dumps(config),
        status="planned",
    )
    session.add(experiment)
    await session.flush()

    for arm in arms_data:
        arm_model = ExperimentArm(
            experiment_id=experiment.id,
            label=arm["label"].strip(),
            target_posts=arm.get("target_posts", 12),
            niche_id=arm.get("niche_id"),
            style_id=arm.get("style_id"),
        )
        session.add(arm_model)

    await session.commit()
    await session.refresh(experiment)

    await record_audit_log(
        session,
        actor=actor,
        action="create_experiment",
        entity="experiments",
        entity_id=experiment.id,
        detail={"name": experiment.name, "phase": experiment.phase, "arms_count": len(arms_data)},
    )

    return experiment


async def update_experiment_status(
    session: AsyncSession,
    experiment_id: str,
    new_status: str,
    actor: str = "admin",
) -> Experiment:
    """Transition experiment status through valid lifecycle stages."""
    if new_status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{new_status}'. Allowed: {VALID_STATUSES}")

    res = await session.execute(
        select(Experiment)
        .options(selectinload(Experiment.arms))
        .where(Experiment.id == experiment_id)
    )
    exp = res.scalar_one_or_none()
    if not exp:
        raise ValueError(f"Experiment '{experiment_id}' not found.")

    current = exp.status
    if current == new_status:
        return exp

    # State machine rules
    valid_transitions = {
        "planned": {"running", "aborted"},
        "running": {"completed", "aborted"},
        "completed": set(),
        "aborted": set(),
    }

    if new_status not in valid_transitions.get(current, set()):
        raise ValueError(f"Cannot transition experiment from '{current}' to '{new_status}'.")

    # If transitioning to 'running', check concurrency rule
    if new_status == "running":
        conflict_res = await session.execute(
            select(Experiment).where(
                Experiment.phase == exp.phase,
                Experiment.status == "running",
                Experiment.id != exp.id,
            )
        )
        conflicting = conflict_res.scalar_one_or_none()
        if conflicting:
            raise ValueError(
                f"Another experiment '{conflicting.name}' is already running in phase '{exp.phase}'. "
                "Only one running experiment per phase is allowed."
            )

    old_status = exp.status
    exp.status = new_status
    exp.updated_at = utc_now_iso()
    await session.commit()
    await session.refresh(exp)

    await record_audit_log(
        session,
        actor=actor,
        action="update_experiment_status",
        entity="experiments",
        entity_id=exp.id,
        detail={"old_status": old_status, "new_status": new_status},
    )

    return exp


async def get_experiment_progress(
    session: AsyncSession,
    experiment_id: str,
) -> dict[str, Any]:
    """Calculate real-time progress for each arm in an experiment."""
    res = await session.execute(
        select(Experiment)
        .options(
            selectinload(Experiment.arms).selectinload(ExperimentArm.niche),
            selectinload(Experiment.arms).selectinload(ExperimentArm.style),
            selectinload(Experiment.arms).selectinload(ExperimentArm.drafts).selectinload(Draft.post).selectinload(Post.metrics),
        )
        .where(Experiment.id == experiment_id)
    )
    exp = res.scalar_one_or_none()
    if not exp:
        raise ValueError(f"Experiment '{experiment_id}' not found.")

    total_target = sum(arm.target_posts for arm in exp.arms)
    total_published = 0
    arm_items = []

    for arm in exp.arms:
        drafts = arm.drafts or []
        total_drafts = len(drafts)
        published_count = 0
        metrics_72h_count = 0

        for d in drafts:
            if d.post:
                published_count += 1
                if any(m.age_bucket == "72h" for m in (d.post.metrics or [])):
                    metrics_72h_count += 1

        total_published += published_count
        progress_pct = round((published_count / arm.target_posts) * 100, 1) if arm.target_posts > 0 else 0.0

        arm_items.append({
            "arm_id": arm.id,
            "label": arm.label,
            "niche_id": arm.niche_id,
            "niche_name": arm.niche.name if arm.niche else None,
            "style_id": arm.style_id,
            "style_name": arm.style.name if arm.style else None,
            "target_posts": arm.target_posts,
            "total_drafts": total_drafts,
            "published_posts": published_count,
            "metrics_completed_72h": metrics_72h_count,
            "progress_pct": min(100.0, progress_pct),
        })

    overall_pct = round((total_published / total_target) * 100, 1) if total_target > 0 else 0.0

    return {
        "experiment_id": exp.id,
        "name": exp.name,
        "phase": exp.phase,
        "status": exp.status,
        "total_target_posts": total_target,
        "total_published_posts": total_published,
        "overall_progress_pct": min(100.0, overall_pct),
        "arms": arm_items,
    }
