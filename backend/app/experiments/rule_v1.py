"""app/experiments/rule_v1.py — Scientific decision rule engine rule_v1 (T-043).

Implements exact decision rules from docs/07 §3:
1. Arm with n < 8 completed 72h posts -> label "data kurang", not ranked.
2. Score formula:
   - If ClickRate available: Score = 0.4 * ER72_norm + 0.4 * ClickRate_norm + 0.2 * Views72_norm
   - If ClickRate not available: Score = 0.8 * ER72_norm + 0.2 * Views72_norm
3. Uses median (not mean) for outlier resistance.
4. Winner recommendation requires:
   - n >= 8
   - top score >= 1.25x runner-up score
   - Otherwise: "belum ada pemenang jelas, perpanjang uji X postingan".
5. Output is strictly recommendation + numbers + n; operator makes the final call.
6. Outlier tagging: post metric > 3x median.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Draft, Experiment, ExperimentArm, LinkClick, Post, PostMetric


def calculate_median(values: list[float]) -> float:
    """Compute exact numeric median of a list of floats."""
    if not values:
        return 0.0
    s = sorted(values)
    length = len(s)
    mid = length // 2
    if length % 2 == 1:
        return float(s[mid])
    return float((s[mid - 1] + s[mid]) / 2.0)


def detect_outliers(
    items: list[dict[str, Any]],
    metric_key: str,
    median_val: float,
    multiplier: float = 3.0,
) -> list[dict[str, Any]]:
    """Identify items whose metric exceeds multiplier * median."""
    if median_val <= 0:
        return []
    threshold = multiplier * median_val
    outliers = []
    for it in items:
        val = it.get(metric_key, 0)
        if val > threshold:
            outliers.append({
                "post_id": it.get("post_id"),
                "value": val,
                "median": median_val,
                "threshold": threshold,
            })
    return outliers


def min_max_normalize(values: dict[str, float]) -> dict[str, float]:
    """Normalize a mapping of id -> float to [0.0, 1.0].

    If all values are identical or only 1 item, assigns 1.0.
    """
    if not values:
        return {}
    vals = list(values.values())
    min_v = min(vals)
    max_v = max(vals)

    if max_v <= min_v:
        # All equal
        return {k: 1.0 for k in values}

    diff = max_v - min_v
    return {k: round((v - min_v) / diff, 4) for k, v in values.items()}


@dataclass
class ArmRuleEvaluation:
    arm_id: str
    label: str
    niche_id: str | None
    niche_name: str | None
    style_id: str | None
    style_name: str | None
    n: int
    insufficient_data: bool  # True if n < 8
    median_views_72: float
    median_er_72: float
    click_rate: float | None
    raw_clicks: int
    score: float
    rank: int | None
    outliers_views: list[dict[str, Any]] = field(default_factory=list)
    outliers_er: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ExperimentRuleEvaluation:
    experiment_id: str
    phase: str
    evaluated_at: str
    status: str
    total_arms: int
    eligible_arms_count: int  # arms with n >= 8
    recommendation: str  # winner_found | no_clear_winner | insufficient_data
    winner_arm_id: str | None
    winner_arm_label: str | None
    runner_up_arm_id: str | None
    score_ratio: float | None  # top_score / runner_up_score
    recommended_extension_posts: int
    explanation: str
    arms: list[ArmRuleEvaluation] = field(default_factory=list)


async def evaluate_experiment_rule_v1(
    session: AsyncSession,
    experiment_id: str,
) -> ExperimentRuleEvaluation:
    """Evaluate an experiment using the rule_v1 scientific formula."""
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

    from app.core.clock import utc_now_iso
    now_iso = utc_now_iso()

    # Preload Benable link clicks for product matching
    clicks_res = await session.execute(select(LinkClick))
    all_clicks = clicks_res.scalars().all()
    clicks_by_product: dict[str, int] = {}
    clicks_by_post: dict[str, int] = {}
    for c in all_clicks:
        if c.product_id:
            clicks_by_product[c.product_id] = clicks_by_product.get(c.product_id, 0) + c.clicks
        if c.post_id:
            clicks_by_post[c.post_id] = clicks_by_post.get(c.post_id, 0) + c.clicks

    arm_evals: list[dict[str, Any]] = []

    for arm in exp.arms:
        # Collect all published posts belonging to this arm that have 72h metrics
        posts_with_72h = []
        for d in (arm.drafts or []):
            if not d.post:
                continue
            p = d.post
            metric_72h = next((m for m in (p.metrics or []) if m.age_bucket == "72h"), None)
            if metric_72h:
                views = metric_72h.views or 0
                likes = metric_72h.likes or 0
                replies = metric_72h.replies or 0
                reposts = metric_72h.reposts or 0
                quotes = metric_72h.quotes or 0
                er = (likes + replies + reposts + quotes) / max(views, 1)

                posts_with_72h.append({
                    "post_id": p.id,
                    "views": views,
                    "er": er,
                    "product_id": d.product_id,
                })

        n = len(posts_with_72h)
        insufficient = n < 8

        views_list = [p["views"] for p in posts_with_72h]
        er_list = [p["er"] for p in posts_with_72h]

        median_views = calculate_median(views_list)
        median_er = calculate_median(er_list)

        outliers_views = detect_outliers(posts_with_72h, "views", median_views, 3.0)
        outliers_er = detect_outliers(posts_with_72h, "er", median_er, 3.0)

        # Calculate click rate
        total_clicks_for_arm = 0
        arm_product_ids = {p["product_id"] for p in posts_with_72h if p["product_id"]}
        for pid in arm_product_ids:
            total_clicks_for_arm += clicks_by_product.get(pid, 0)
        for p in posts_with_72h:
            total_clicks_for_arm += clicks_by_post.get(p["post_id"], 0)

        total_views_sum = sum(views_list)
        if total_clicks_for_arm > 0 and total_views_sum > 0:
            click_rate = round((total_clicks_for_arm / total_views_sum) * 1000, 2)
        else:
            click_rate = None

        arm_evals.append({
            "arm_id": arm.id,
            "label": arm.label,
            "niche_id": arm.niche_id,
            "niche_name": arm.niche.name if arm.niche else None,
            "style_id": arm.style_id,
            "style_name": arm.style.name if arm.style else None,
            "n": n,
            "insufficient_data": insufficient,
            "median_views_72": median_views,
            "median_er_72": median_er,
            "click_rate": click_rate,
            "raw_clicks": total_clicks_for_arm,
            "outliers_views": outliers_views,
            "outliers_er": outliers_er,
        })

    # Normalization & Score calculation (docs/07 §3 Aturan 2)
    # Check if any arm has click data
    has_any_clicks = any(a["click_rate"] is not None for a in arm_evals)

    views_map = {a["arm_id"]: a["median_views_72"] for a in arm_evals}
    er_map = {a["arm_id"]: a["median_er_72"] for a in arm_evals}
    click_map = {a["arm_id"]: (a["click_rate"] or 0.0) for a in arm_evals}

    norm_views = min_max_normalize(views_map)
    norm_er = min_max_normalize(er_map)
    norm_click = min_max_normalize(click_map) if has_any_clicks else {}

    for a in arm_evals:
        aid = a["arm_id"]
        v_norm = norm_views.get(aid, 0.0)
        er_norm = norm_er.get(aid, 0.0)

        if has_any_clicks and a["click_rate"] is not None:
            c_norm = norm_click.get(aid, 0.0)
            score = round(0.4 * er_norm + 0.4 * c_norm + 0.2 * v_norm, 4)
        else:
            # Transfer weight to ER72
            score = round(0.8 * er_norm + 0.2 * v_norm, 4)

        a["score"] = score

    # Rank eligible arms (n >= 8)
    eligible_arms = [a for a in arm_evals if not a["insufficient_data"]]
    eligible_arms.sort(key=lambda x: x["score"], reverse=True)

    for rank_idx, a in enumerate(eligible_arms, start=1):
        a["rank"] = rank_idx

    for a in arm_evals:
        if a["insufficient_data"]:
            a["rank"] = None

    # Decision Recommendation (docs/07 §3 Aturan 4 & 5)
    winner_arm_id = None
    winner_arm_label = None
    runner_up_arm_id = None
    score_ratio = None
    recommended_extension = 0

    if not eligible_arms:
        recommendation = "insufficient_data"
        max_n = max((a["n"] for a in arm_evals), default=0)
        recommended_extension = max(5, 8 - max_n)
        explanation = (
            f"Data kurang across all arms (all n < 8). "
            f"Highest sample size is n={max_n}. Extend test by at least {recommended_extension} posts."
        )

    elif len(eligible_arms) == 1:
        # Only 1 arm reached n >= 8
        top = eligible_arms[0]
        recommendation = "insufficient_data"
        explanation = (
            f"Only 1 arm ('{top['label']}', n={top['n']}) has completed n >= 8 posts. "
            "Need at least 2 arms with n >= 8 for valid comparison."
        )
        recommended_extension = 4

    else:
        top = eligible_arms[0]
        runner_up = eligible_arms[1]
        runner_up_arm_id = runner_up["arm_id"]

        # Prevent div by zero
        r_score = max(runner_up["score"], 0.0001)
        ratio = round(top["score"] / r_score, 2)
        score_ratio = ratio

        # Threshold: top score >= 1.25x runner-up
        if ratio >= 1.25:
            recommendation = "winner_found"
            winner_arm_id = top["arm_id"]
            winner_arm_label = top["label"]
            explanation = (
                f"Arm '{top['label']}' is the recommended winner with score {top['score']:.4f} "
                f"({ratio:.2f}x runner-up '{runner_up['label']}' with score {runner_up['score']:.4f}, n={top['n']})."
            )
        else:
            recommendation = "no_clear_winner"
            recommended_extension = max(5, 12 - top["n"])
            explanation = (
                f"No clear winner yet. Top arm '{top['label']}' ({top['score']:.4f}) is only "
                f"{ratio:.2f}x of runner-up '{runner_up['label']}' ({runner_up['score']:.4f}), which is < 1.25x threshold. "
                f"Extend test by {recommended_extension} posts."
            )

    built_arms = [
        ArmRuleEvaluation(
            arm_id=a["arm_id"],
            label=a["label"],
            niche_id=a["niche_id"],
            niche_name=a["niche_name"],
            style_id=a["style_id"],
            style_name=a["style_name"],
            n=a["n"],
            insufficient_data=a["insufficient_data"],
            median_views_72=a["median_views_72"],
            median_er_72=a["median_er_72"],
            click_rate=a["click_rate"],
            raw_clicks=a["raw_clicks"],
            score=a["score"],
            rank=a["rank"],
            outliers_views=a["outliers_views"],
            outliers_er=a["outliers_er"],
        )
        for a in arm_evals
    ]

    return ExperimentRuleEvaluation(
        experiment_id=exp.id,
        phase=exp.phase,
        evaluated_at=now_iso,
        status=exp.status,
        total_arms=len(arm_evals),
        eligible_arms_count=len(eligible_arms),
        recommendation=recommendation,
        winner_arm_id=winner_arm_id,
        winner_arm_label=winner_arm_label,
        runner_up_arm_id=runner_up_arm_id,
        score_ratio=score_ratio,
        recommended_extension_posts=recommended_extension,
        explanation=explanation,
        arms=built_arms,
    )
