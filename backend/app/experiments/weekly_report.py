"""app/experiments/weekly_report.py — Weekly Performance & Experimentation Report Generator (T-043).

Generates comprehensive weekly summaries (docs/07 §6):
1. Published posts count & aggregate engagement.
2. Active experiments rule_v1 evaluation with median ER72/Views72, n, and recommendations.
3. System incidents summary (unresolved, critical).
4. Operator review workload (approved, rejected, pending queue).
5. Concrete action advice for the operator.
6. Outputs both structured JSON and concise Telegram-ready format.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.clock import utc_now, utc_now_iso
from app.db.models import Account, Draft, Experiment, Incident, Post, PostMetric
from app.experiments.rule_v1 import evaluate_experiment_rule_v1


async def generate_weekly_report(
    session: AsyncSession,
    days_back: int = 7,
) -> dict[str, Any]:
    """Compile performance, experiment evaluations, and operational metrics for the period."""
    now = utc_now()
    cutoff_dt = now - timedelta(days=days_back)
    cutoff_iso = cutoff_dt.isoformat()
    period_start = cutoff_iso[:10]
    period_end = now.isoformat()[:10]

    # 1. Published posts during period
    posts_q = (
        select(Post)
        .options(selectinload(Post.metrics), selectinload(Post.draft))
        .where(Post.published_at >= cutoff_iso)
        .order_by(Post.published_at.desc())
    )
    posts_res = await session.execute(posts_q)
    recent_posts = posts_res.scalars().all()

    total_published = len(recent_posts)
    total_views = 0
    total_engagements = 0

    for p in recent_posts:
        max_v = 0
        max_eng = 0
        for m in (p.metrics or []):
            v = m.views or 0
            eng = (m.likes or 0) + (m.replies or 0) + (m.reposts or 0) + (m.quotes or 0)
            max_v = max(max_v, v)
            max_eng = max(max_eng, eng)
        total_views += max_v
        total_engagements += max_eng

    avg_er = round((total_engagements / max(total_views, 1)) * 100, 2) if total_views > 0 else 0.0

    # 2. Operator review workload during period
    draft_counts_q = (
        select(Draft.status, func.count(Draft.id))
        .where(Draft.created_at >= cutoff_iso)
        .group_by(Draft.status)
    )
    draft_res = await session.execute(draft_counts_q)
    draft_counts = dict(draft_res.all())

    # Current pending queue
    pending_q = await session.execute(
        select(func.count(Draft.id)).where(Draft.status == "pending_review")
    )
    current_pending = pending_q.scalar_one() or 0

    workload = {
        "drafts_created_this_period": sum(draft_counts.values()),
        "approved": draft_counts.get("approved", 0) + draft_counts.get("scheduled", 0) + draft_counts.get("published", 0),
        "rejected": draft_counts.get("rejected", 0) + draft_counts.get("rejected_auto", 0),
        "current_pending_queue": current_pending,
    }

    # 3. Incidents summary
    inc_q = select(Incident).where(Incident.created_at >= cutoff_iso)
    inc_res = await session.execute(inc_q)
    incidents = inc_res.scalars().all()

    unresolved_inc = [i for i in incidents if not i.resolved_at]
    critical_inc = [i for i in incidents if i.severity == "critical"]

    incident_summary = {
        "total_incidents": len(incidents),
        "unresolved_count": len(unresolved_inc),
        "critical_count": len(critical_inc),
        "recent_incidents": [
            {"code": i.code, "severity": i.severity, "detail": i.detail, "at": i.created_at}
            for i in incidents[:5]
        ],
    }

    # 4. Active Experiments evaluation
    exp_q = select(Experiment).where(Experiment.status.in_(["running", "completed"]))
    exp_res = await session.execute(exp_q)
    active_experiments = exp_res.scalars().all()

    experiment_evaluations = []
    actions_suggested = []

    for exp in active_experiments:
        try:
            eval_result = await evaluate_experiment_rule_v1(session, exp.id)
            eval_dict = {
                "experiment_id": eval_result.experiment_id,
                "phase": eval_result.phase,
                "status": eval_result.status,
                "recommendation": eval_result.recommendation,
                "winner_arm_label": eval_result.winner_arm_label,
                "score_ratio": eval_result.score_ratio,
                "explanation": eval_result.explanation,
                "recommended_extension_posts": eval_result.recommended_extension_posts,
                "arms": [
                    {
                        "arm_id": a.arm_id,
                        "label": a.label,
                        "n": a.n,
                        "insufficient_data": a.insufficient_data,
                        "median_views_72": a.median_views_72,
                        "median_er_72": round(a.median_er_72 * 100, 2),  # in %
                        "click_rate": a.click_rate,
                        "score": a.score,
                        "rank": a.rank,
                        "outliers_count": len(a.outliers_views) + len(a.outliers_er),
                    }
                    for a in eval_result.arms
                ],
            }
            experiment_evaluations.append(eval_dict)

            # Suggest operator actions based on rule_v1
            if eval_result.recommendation == "winner_found":
                actions_suggested.append(
                    f"🏆 Eksperimen '{exp.phase}': Arm '{eval_result.winner_arm_label}' memenuhi syarat pemenang. "
                    "Operator dapat menandai selesai dan beralih ke fase berikutnya."
                )
            elif eval_result.recommendation == "no_clear_winner":
                actions_suggested.append(
                    f"⚖️ Eksperimen '{exp.phase}': Belum ada pemenang jelas. "
                    f"Perpanjang uji coba sekitar {eval_result.recommended_extension_posts} postingan."
                )
            else:
                actions_suggested.append(
                    f"📊 Eksperimen '{exp.phase}': Data kurang (n < 8 per arm). "
                    f"Lanjutkan publikasi hingga sampel terpenuhi."
                )
        except Exception:
            pass

    if not actions_suggested:
        actions_suggested.append("✅ Operasi berjalan normal. Lanjutkan review draf sesuai jadwal harian.")

    if unresolved_inc:
        actions_suggested.insert(0, f"⚠️ Ada {len(unresolved_inc)} insiden belum terselesaikan yang memerlukan perhatian.")

    return {
        "period_start": period_start,
        "period_end": period_end,
        "generated_at": now.isoformat(),
        "total_posts_published": total_published,
        "total_views": total_views,
        "total_engagements": total_engagements,
        "average_er_pct": avg_er,
        "operator_workload": workload,
        "incidents": incident_summary,
        "experiments": experiment_evaluations,
        "suggested_actions": actions_suggested,
    }


def format_weekly_report_telegram(report: dict[str, Any]) -> str:
    """Format weekly report dict into clear, structured Telegram markdown."""
    lines = [
        f"📅 <b>Laporan Mingguan Threads</b> ({report['period_start']} s/d {report['period_end']})",
        "",
        f"🚀 <b>Publikasi & Performa:</b>",
        f"• Postingan Terbit: <b>{report['total_posts_published']}</b>",
        f"• Total Views: <b>{report['total_views']:,}</b>",
        f"• Rata-rata ER: <b>{report['average_er_pct']:.2f}%</b>",
        "",
        f"👨‍💻 <b>Beban Review Operator:</b>",
        f"• Disetujui: <b>{report['operator_workload']['approved']}</b>",
        f"• Ditolak: <b>{report['operator_workload']['rejected']}</b>",
        f"• Antrean Saat Ini: <b>{report['operator_workload']['current_pending_queue']} draf</b>",
        "",
    ]

    # Experiments section
    exps = report.get("experiments", [])
    if exps:
        lines.append("🧪 <b>Evaluasi Eksperimen (rule_v1):</b>")
        for e in exps:
            status_icon = "🟢" if e["status"] == "running" else "🏁"
            lines.append(f"{status_icon} <b>Fase: {e['phase']}</b> ({e['status']})")
            for a in e.get("arms", []):
                data_tag = " [data kurang]" if a["insufficient_data"] else f" [Rank #{a['rank']}]"
                cr_str = f", CR: {a['click_rate']}" if a["click_rate"] is not None else ""
                lines.append(
                    f"  • <b>{a['label']}</b> (n={a['n']}{data_tag}): "
                    f"ER={a['median_er_72']:.2f}%, Views={a['median_views_72']:.0f}{cr_str}"
                )
            lines.append(f"  💡 <i>{e['explanation']}</i>")
            lines.append("")
    else:
        lines.append("🧪 <i>Belum ada eksperimen aktif.</i>\n")

    # Incidents section
    inc = report.get("incidents", {})
    if inc.get("unresolved_count", 0) > 0:
        lines.append(f"⚠️ <b>Insiden:</b> {inc['unresolved_count']} insiden aktif / belum diselesaikan!\n")

    # Suggested actions
    lines.append("🎯 <b>Rekomendasi Tindakan:</b>")
    for act in report.get("suggested_actions", []):
        lines.append(f"• {act}")

    return "\n".join(lines)
