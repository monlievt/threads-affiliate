"""app/safety/automation_policy.py — Automation Mode, Full-Auto Eligibility, and Auto-Downgrade Engine (T-050).

Implements strict platform safety requirements from docs/06 §6:
1. Automation Modes:
   - 'manual_approve': 100% of passing drafts require operator review (status='pending_review').
   - 'auto_sampled': Passing drafts are randomly sampled at sample_review_pct (e.g. 30%) for
     manual review; non-sampled passing drafts are auto-approved (status='approved').
   - 'full_auto': 100% of passing drafts are auto-approved (status='approved').
2. Full-Auto Eligibility Criteria (evaluated over the last 14 days):
   - Condition 1: 0 critical incidents.
   - Condition 2: Final validator rejection rate < 2%.
   - Condition 3: Operator manual rejection rate < 15% on at least 40 reviewed drafts.
   - Condition 4: Threads token valid and Kill Switch OFF.
   - Condition 5: Worker heartbeat healthy (recent heartbeat within 120s).
3. Automatic Downgrade to 'manual_approve':
   - Triggered if there is >= 1 'critical' incident in the last 7 days, OR
   - Triggered if there are >= 2 'warning' incidents in the last 7 days.
   - Immediately reverts account to 'manual_approve', logs an audit trail event,
     and records an incident.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_log
from app.core.clock import utc_now, utc_now_iso
from app.core.logging import get_logger
from app.db.models import Account, Draft, Incident
from app.scheduler.heartbeat import get_worker_heartbeat_info
from app.safety.killswitch import is_kill_switch_active

log = get_logger(__name__)


def determine_draft_initial_status(
    account: Account,
    val_passed: bool,
    reject_reason: str | None = None,
) -> tuple[str, str | None]:
    """Determine initial status of a generated draft based on account automation mode.

    Returns:
        (status, note_or_reason)
    """
    if not val_passed:
        return "rejected_auto", reject_reason or "Failed safety content validators"

    mode = account.automation_mode or "manual_approve"

    if mode == "manual_approve":
        return "pending_review", None

    if mode == "full_auto":
        return "approved", "Auto-approved via full_auto mode"

    if mode == "auto_sampled":
        sample_pct = getattr(account, "sample_review_pct", 30) or 30
        sample_pct = max(10, min(100, sample_pct))
        roll = random.uniform(0.0, 100.0)
        if roll < sample_pct:
            return "pending_review", f"Sampled for manual review ({sample_pct}% review sample)"
        return "approved", f"Auto-approved via auto_sampled non-review selection (roll {roll:.1f} >= {sample_pct}%)"

    return "pending_review", None


async def evaluate_auto_downgrade(
    session: AsyncSession,
    account: Account,
    actor: str = "safety_system",
) -> tuple[bool, str | None]:
    """Check if safety incidents require automatic downgrade to 'manual_approve' (docs/06 §6).

    Rules:
    - >= 1 'critical' incident in last 7 days -> Downgrade
    - >= 2 'warning' incidents in last 7 days -> Downgrade

    Returns:
        (downgraded: bool, reason: str | None)
    """
    if account.automation_mode == "manual_approve":
        return False, None

    now = utc_now()
    seven_days_ago = (now - timedelta(days=7)).isoformat()

    # Query incidents in past 7 days
    inc_res = await session.execute(
        select(Incident).where(
            Incident.created_at >= seven_days_ago,
            Incident.severity.in_(["warning", "critical"]),
        )
    )
    incidents = inc_res.scalars().all()

    critical_count = sum(1 for i in incidents if i.severity == "critical")
    warning_count = sum(1 for i in incidents if i.severity == "warning")

    downgrade_reasons: list[str] = []
    if critical_count >= 1:
        downgrade_reasons.append(f"{critical_count} insiden critical dalam 7 hari terakhir")
    if warning_count >= 2:
        downgrade_reasons.append(f"{warning_count} insiden warning dalam 7 hari terakhir")

    if not downgrade_reasons:
        return False, None

    reason_str = " & ".join(downgrade_reasons)
    old_mode = account.automation_mode
    account.automation_mode = "manual_approve"
    account.updated_at = utc_now_iso()

    # Record incident for the auto-downgrade event
    downgrade_incident = Incident(
        account_id=account.id,
        code="AUTO_DOWNGRADE_TRIGGERED",
        severity="warning",
        detail=f"Sistem menurunkan mode otomatisasi dari '{old_mode}' ke 'manual_approve'. Penyebab: {reason_str}.",
    )
    session.add(downgrade_incident)

    await session.commit()
    await session.refresh(account)

    # Log audit event
    await record_audit_log(
        session,
        actor=actor,
        action="auto_downgrade",
        entity="accounts",
        entity_id=account.id,
        detail={
            "old_mode": old_mode,
            "new_mode": "manual_approve",
            "critical_count_7d": critical_count,
            "warning_count_7d": warning_count,
            "reason": reason_str,
        },
    )

    log.warning(
        "AUTOMATION AUTO-DOWNGRADE TRIGGERED",
        account_id=account.id,
        old_mode=old_mode,
        reason=reason_str,
    )
    return True, reason_str


@dataclass
class CriterionResult:
    key: str
    label: str
    required: str
    current: str
    passed: bool


@dataclass
class FullAutoEligibilityResult:
    eligible: bool
    summary_reason: str
    criteria: dict[str, CriterionResult]


async def evaluate_full_auto_eligibility(
    session: AsyncSession,
    account: Account,
) -> FullAutoEligibilityResult:
    """Evaluate whether the account qualifies for full_auto autonomous mode (docs/06 §6).

    Must meet all 5 criteria over the last 14 days:
    1. Zero critical incidents.
    2. Final validator rejection rate < 2%.
    3. Operator rejection rate < 15% on at least 40 reviewed drafts.
    4. Threads token valid and Kill Switch OFF.
    5. Worker heartbeat healthy (< 120s ago).
    """
    now = utc_now()
    fourteen_days_ago = (now - timedelta(days=14)).isoformat()

    # Criterion 1: Zero critical incidents in last 14 days
    crit_res = await session.execute(
        select(func.count(Incident.id)).where(
            Incident.created_at >= fourteen_days_ago,
            Incident.severity == "critical",
        )
    )
    critical_count = crit_res.scalar_one() or 0
    c1_passed = critical_count == 0

    # Criterion 2: Validator rejection rate < 2% in last 14 days
    drafts_14d_q = await session.execute(
        select(Draft.status, func.count(Draft.id))
        .where(Draft.created_at >= fourteen_days_ago)
        .group_by(Draft.status)
    )
    draft_status_map = dict(drafts_14d_q.all())
    total_generated_14d = sum(draft_status_map.values())
    rejected_auto_14d = draft_status_map.get("rejected_auto", 0)

    val_reject_rate = (rejected_auto_14d / total_generated_14d) if total_generated_14d > 0 else 0.0
    # If no drafts generated yet, cannot establish < 2% track record
    c2_passed = (total_generated_14d >= 20) and (val_reject_rate < 0.02)

    # Criterion 3: Operator rejection rate < 15% on at least 40 reviewed drafts
    approved_14d = (
        draft_status_map.get("approved", 0)
        + draft_status_map.get("scheduled", 0)
        + draft_status_map.get("publishing", 0)
        + draft_status_map.get("published", 0)
    )
    rejected_operator_14d = draft_status_map.get("rejected", 0)
    total_reviewed_14d = approved_14d + rejected_operator_14d

    op_reject_rate = (rejected_operator_14d / total_reviewed_14d) if total_reviewed_14d > 0 else 0.0
    c3_passed = (total_reviewed_14d >= 40) and (op_reject_rate < 0.15)

    # Criterion 4: Threads token valid & Kill switch OFF
    from app.core.security import get_token_status
    token_status = get_token_status(account)
    ks_active = await is_kill_switch_active(session)
    c4_passed = token_status["valid"] and not ks_active

    # Criterion 5: Worker heartbeat healthy (recorded within last 120s)
    hb_info = await get_worker_heartbeat_info(session, max_stale_seconds=120)
    hb_passed = hb_info.get("is_alive", False)
    hb_lag_sec = int(hb_info.get("age_seconds") or 9999)

    eligible = c1_passed and c2_passed and c3_passed and c4_passed and hb_passed

    criteria = {
        "zero_critical_incidents": CriterionResult(
            key="zero_critical_incidents",
            label="0 insiden critical dalam 14 hari terakhir",
            required="0 insiden",
            current=f"{critical_count} insiden",
            passed=c1_passed,
        ),
        "validator_rejection_rate": CriterionResult(
            key="validator_rejection_rate",
            label="Tingkat penolakan validator tahap akhir < 2% (minimal 20 draf dibuat)",
            required="< 2.0% (min 20 draf)",
            current=f"{val_reject_rate * 100:.1f}% ({rejected_auto_14d}/{total_generated_14d})",
            passed=c2_passed,
        ),
        "operator_rejection_rate": CriterionResult(
            key="operator_rejection_rate",
            label="Tingkat penolakan manual operator < 15% pada minimal 40 draf yang ditinjau",
            required="< 15.0% (min 40 draf)",
            current=f"{op_reject_rate * 100:.1f}% ({rejected_operator_14d}/{total_reviewed_14d})",
            passed=c3_passed,
        ),
        "account_and_killswitch_ready": CriterionResult(
            key="account_and_killswitch_ready",
            label="Token Threads valid dan Kill Switch tidak aktif",
            required="Token Valid & Kill Switch OFF",
            current="Siap" if c4_passed else "Tidak Siap (Kill Switch ON atau Token Expired)",
            passed=c4_passed,
        ),
        "worker_heartbeat_healthy": CriterionResult(
            key="worker_heartbeat_healthy",
            label="Worker uptime sehat (heartbeat aktif < 120 detik)",
            required="≤ 120 detik",
            current=f"{hb_lag_sec} detik lalu" if latest_hb else "Belum ada heartbeat",
            passed=hb_passed,
        ),
    }

    if eligible:
        summary = "Akun memenuhi seluruh 5 syarat kelayakan ilmiah untuk beralih ke mode full_auto (otonom)."
    else:
        unmet = [c.label for c in criteria.values() if not c.passed]
        summary = f"Syarat belum terpenuhi: {'; '.join(unmet)}."

    return FullAutoEligibilityResult(
        eligible=eligible,
        summary_reason=summary,
        criteria=criteria,
    )
