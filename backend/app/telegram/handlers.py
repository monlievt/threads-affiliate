"""app/telegram/handlers.py — Command and Callback handlers for Telegram Bot.

Implements strict safety controls:
1. Admin-only check on every command & callback.
2. Idempotent action handling on callback buttons (prevents duplicate approvals/rejections).
3. Mandatory confirmation on /resume to re-arm publishing.
4. Comprehensive audit logging for all operator actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.content.llm.usage import get_today_call_count
from app.core.audit import record_audit_log
from app.core.logging import get_logger
from app.core.clock import utc_now_iso
from app.db.models import Account, Draft, LlmUsage, Post
from app.safety.killswitch import get_kill_switch_status, set_kill_switch
from app.safety.warmup import get_warmup_tier
from app.telegram.formatter import format_draft_card
from app.telegram.security import is_authorized_admin_chat
from app.telegram.service import HandlerResponse

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Command Handlers
# ---------------------------------------------------------------------------
async def handle_start(
    chat_id: int | str,
    session: AsyncSession,
) -> HandlerResponse:
    """Handle /start command — welcome and directory."""
    if not await is_authorized_admin_chat(chat_id, session, action_attempted="/start"):
        return HandlerResponse(text="⛔ Unauthorized. Your access attempt has been logged.")

    text = (
        "🤖 <b>Threads Affiliate Telegram Bot</b>\n\n"
        "Available commands:\n"
        "• <code>/status</code> — System health, kill switch, and queue overview\n"
        "• <code>/queue</code> — Review pending drafts awaiting approval\n"
        "• <code>/pause</code> — Emergency stop (Engage Kill Switch)\n"
        "• <code>/resume</code> — Re-arm publishing (requires confirmation)\n"
        "• <code>/quota</code> — Daily post limits and LLM budget usage\n"
        "• <code>/report</code> — Summary of today's publishing performance"
    )
    return HandlerResponse(text=text)


async def handle_status(
    chat_id: int | str,
    session: AsyncSession,
) -> HandlerResponse:
    """Handle /status command — system status and draft metrics."""
    if not await is_authorized_admin_chat(chat_id, session, action_attempted="/status"):
        return HandlerResponse(text="⛔ Unauthorized.")

    # 1. Kill Switch
    ks_info = await get_kill_switch_status(session)
    ks_icon = "🔴 ON (PAUSED)" if ks_info["active"] else "🟢 OFF (ARMED)"

    # 2. Account automation mode
    acc_res = await session.execute(select(Account).limit(1))
    account = acc_res.scalar_one_or_none()
    auto_mode = account.automation_mode if account else "Not configured"

    # 3. Draft metrics
    counts_query = (
        select(Draft.status, func.count(Draft.id))
        .group_by(Draft.status)
    )
    counts_res = await session.execute(counts_query)
    status_counts = dict(counts_res.all())

    pending = status_counts.get("pending_review", 0)
    approved = status_counts.get("approved", 0)
    scheduled = status_counts.get("scheduled", 0)
    published = status_counts.get("published", 0)
    rejected = status_counts.get("rejected", 0) + status_counts.get("rejected_auto", 0)

    text = (
        f"📊 <b>System Status</b>\n\n"
        f"• <b>Kill Switch:</b> {ks_icon}\n"
        f"• <b>Reason:</b> {ks_info.get('reason') or 'N/A'}\n"
        f"• <b>Automation Mode:</b> <code>{auto_mode}</code>\n\n"
        f"<b>Draft Pipeline:</b>\n"
        f"⏳ Pending Review: <b>{pending}</b>\n"
        f"✅ Approved: <b>{approved}</b>\n"
        f"🕒 Scheduled: <b>{scheduled}</b>\n"
        f"🚀 Published: <b>{published}</b>\n"
        f"❌ Rejected: <b>{rejected}</b>"
    )
    return HandlerResponse(text=text)


async def handle_queue(
    chat_id: int | str,
    session: AsyncSession,
) -> HandlerResponse:
    """Handle /queue command — fetch top draft pending review."""
    if not await is_authorized_admin_chat(chat_id, session, action_attempted="/queue"):
        return HandlerResponse(text="⛔ Unauthorized.")

    # Fetch earliest pending review draft
    query = (
        select(Draft)
        .options(selectinload(Draft.niche), selectinload(Draft.style))
        .where(Draft.status == "pending_review")
        .order_by(Draft.created_at.asc())
        .limit(1)
    )
    res = await session.execute(query)
    draft = res.scalar_one_or_none()

    if not draft:
        return HandlerResponse(text="✨ Tidak ada draf yang menunggu review saat ini.")

    text, buttons = format_draft_card(
        draft=draft,
        niche_name=draft.niche.name if draft.niche else None,
        style_name=draft.style.name if draft.style else None,
    )
    return HandlerResponse(text=text, buttons=buttons)


async def handle_pause(
    chat_id: int | str,
    session: AsyncSession,
) -> HandlerResponse:
    """Handle /pause command — emergency kill switch activation."""
    if not await is_authorized_admin_chat(chat_id, session, action_attempted="/pause"):
        return HandlerResponse(text="⛔ Unauthorized.")

    await set_kill_switch(
        session,
        active=True,
        reason="Emergency pause via Telegram /pause",
        actor=f"telegram:{chat_id}",
    )
    text = (
        "🚨 <b>KILL SWITCH ENGAGED (ON)</b>\n\n"
        "Semua proses penerbitan dan penjadwalan Threads telah dihentikan secara instan (≤ 5 detik).\n"
        "Gunakan <code>/resume</code> jika siap mengaktifkan kembali."
    )
    return HandlerResponse(text=text)


async def handle_resume(
    chat_id: int | str,
    args: str,
    session: AsyncSession,
) -> HandlerResponse:
    """Handle /resume command — requires explicit confirmation to disarm kill switch."""
    if not await is_authorized_admin_chat(chat_id, session, action_attempted="/resume"):
        return HandlerResponse(text="⛔ Unauthorized.")

    clean_args = args.strip().lower()
    if clean_args not in ("confirm", "ya", "yes"):
        # Require confirmation
        buttons = [
            [
                {"text": "✅ Ya, Aktifkan Kembali", "callback_data": "sys:resume:confirm"},
                {"text": "❌ Batal", "callback_data": "sys:resume:cancel"},
            ]
        ]
        text = (
            "⚠️ <b>Konfirmasi Pengaktifan Kembali (Resume)</b>\n\n"
            "Apakah Anda yakin ingin mematikan Kill Switch dan mengizinkan posting otomatis berjalan?\n\n"
            "Ketik <code>/resume confirm</code> atau klik tombol di bawah:"
        )
        return HandlerResponse(text=text, buttons=buttons)

    # Disarm kill switch
    await set_kill_switch(
        session,
        active=False,
        reason="Disarmed via Telegram /resume confirmation",
        actor=f"telegram:{chat_id}",
    )
    text = (
        "🟢 <b>KILL SWITCH DISARMED (OFF)</b>\n\n"
        "Sistem telah diaktifkan kembali. Penerbitan postingan akan berjalan sesuai jadwal."
    )
    return HandlerResponse(text=text)


async def handle_quota(
    chat_id: int | str,
    session: AsyncSession,
) -> HandlerResponse:
    """Handle /quota command — daily post limit and LLM budget."""
    if not await is_authorized_admin_chat(chat_id, session, action_attempted="/quota"):
        return HandlerResponse(text="⛔ Unauthorized.")

    today_prefix = utc_now_iso()[:10]

    # LLM budget today
    llm_count = await get_today_call_count(session)

    # Posts published today
    posts_res = await session.execute(
        select(func.count(Post.id)).where(Post.published_at.like(f"{today_prefix}%"))
    )
    posts_today = posts_res.scalar_one() or 0

    # Account warmup tier
    acc_res = await session.execute(select(Account).limit(1))
    account = acc_res.scalar_one_or_none()
    warmup_tier = get_warmup_tier(account.warmup_started_at) if account else None

    tier_desc = f"Week {warmup_tier.week}" if warmup_tier else "Standard"
    max_posts = warmup_tier.max_posts_per_day if warmup_tier else 5
    min_interval = warmup_tier.min_interval_minutes if warmup_tier else 120

    text = (
        f"📈 <b>Daily Quota & Budget</b> ({today_prefix})\n\n"
        f"• <b>Warmup Status:</b> {tier_desc}\n"
        f"• <b>Threads Posts Today:</b> {posts_today} / {max_posts} posts\n"
        f"• <b>Min Post Interval:</b> {min_interval} minutes\n"
        f"• <b>LLM Calls Today:</b> {llm_count} calls\n"
    )
    return HandlerResponse(text=text)


async def handle_report(
    chat_id: int | str,
    session: AsyncSession,
) -> HandlerResponse:
    """Handle /report command — weekly performance summary with rule_v1 evaluation."""
    if not await is_authorized_admin_chat(chat_id, session, action_attempted="/report"):
        return HandlerResponse(text="⛔ Unauthorized.")

    from app.experiments.weekly_report import format_weekly_report_telegram, generate_weekly_report

    report_data = await generate_weekly_report(session, days_back=7)
    text = format_weekly_report_telegram(report_data)
    return HandlerResponse(text=text)


# ---------------------------------------------------------------------------
# Interactive Callback Handler (with strict idempotency)
# ---------------------------------------------------------------------------
async def handle_callback(
    chat_id: int | str,
    callback_data: str,
    session: AsyncSession,
) -> HandlerResponse:
    """Process interactive button clicks with strict idempotency and audit trail."""
    if not await is_authorized_admin_chat(chat_id, session, action_attempted=f"callback:{callback_data}"):
        return HandlerResponse(text="⛔ Unauthorized action.")

    parts = callback_data.split(":")

    # 1. System Resume confirmation
    if callback_data == "sys:resume:confirm":
        await set_kill_switch(
            session,
            active=False,
            reason="Confirmed via Telegram interactive button",
            actor=f"telegram:{chat_id}",
        )
        return HandlerResponse(text="🟢 Kill switch dinonaktifkan (OFF). Sistem publishing aktif.")

    if callback_data == "sys:resume:cancel":
        return HandlerResponse(text="❌ Konfirmasi dibatalkan. Kill switch tetap ON (berhenti).")

    # 2. Draft action: draft:{id}:{action}:{version}
    if parts[0] == "draft" and len(parts) >= 3:
        draft_id = parts[1]
        action = parts[2]
        version = parts[3] if len(parts) > 3 else "v1"

        draft_res = await session.execute(select(Draft).where(Draft.id == draft_id))
        draft = draft_res.scalar_one_or_none()
        if not draft:
            return HandlerResponse(
                text=f"⚠️ Draf #{draft_id[:8]} tidak ditemukan di database.",
                already_processed=True,
            )

        short_id = draft.id[:8]

        # Action: Approve
        if action == "approve":
            # Idempotency check: draft already approved, scheduled, or published
            if draft.status in ("approved", "scheduled", "publishing", "published"):
                log.info("Duplicate approve callback ignored", draft_id=draft.id, status=draft.status)
                return HandlerResponse(
                    text=f"⚠️ Draf #{short_id} sudah disetujui ({draft.status}) sebelumnya. Tidak ada aksi ganda.",
                    already_processed=True,
                )

            if draft.status != "pending_review":
                return HandlerResponse(
                    text=f"⚠️ Draf #{short_id} berstatus '{draft.status}', tidak dapat disetujui.",
                    already_processed=True,
                )

            # Apply transition
            draft.status = "approved"
            draft.reviewed_at = utc_now_iso()
            draft.updated_at = utc_now_iso()
            await session.commit()
            await session.refresh(draft)

            await record_audit_log(
                session,
                actor=f"telegram:{chat_id}",
                action="approve_telegram",
                entity="drafts",
                entity_id=draft.id,
                detail={"version": version, "new_status": "approved"},
            )

            return HandlerResponse(
                text=f"✅ <b>Draf #{short_id} disetujui!</b> Akan dijadwalkan oleh scheduler.",
                already_processed=False,
            )

        # Action: Reject
        if action == "reject":
            # Idempotency check: draft already rejected or cancelled
            if draft.status in ("rejected", "cancelled", "rejected_auto"):
                log.info("Duplicate reject callback ignored", draft_id=draft.id, status=draft.status)
                return HandlerResponse(
                    text=f"⚠️ Draf #{short_id} sudah ditolak ({draft.status}) sebelumnya. Tidak ada aksi ganda.",
                    already_processed=True,
                )

            draft.status = "rejected"
            draft.reject_reason = "Rejected by operator via Telegram review"
            draft.reviewed_at = utc_now_iso()
            draft.updated_at = utc_now_iso()
            await session.commit()
            await session.refresh(draft)

            await record_audit_log(
                session,
                actor=f"telegram:{chat_id}",
                action="reject_telegram",
                entity="drafts",
                entity_id=draft.id,
                detail={"version": version, "new_status": "rejected"},
            )

            return HandlerResponse(
                text=f"❌ <b>Draf #{short_id} ditolak.</b>",
                already_processed=False,
            )

        # Action: Regenerate
        if action == "regenerate":
            if draft.status in ("published", "publishing"):
                return HandlerResponse(
                    text=f"⚠️ Draf #{short_id} sudah dipublikasikan, tidak dapat diregenerasi.",
                    already_processed=True,
                )

            await record_audit_log(
                session,
                actor=f"telegram:{chat_id}",
                action="regenerate_telegram_requested",
                entity="drafts",
                entity_id=draft.id,
                detail={"version": version},
            )

            return HandlerResponse(
                text=f"🔁 <b>Permintaan regenerasi draf #{short_id} dicatat.</b> Mesin konten akan membuat varian baru.",
                already_processed=False,
            )

    return HandlerResponse(text=f"Aksi tidak dikenali: {callback_data!r}")
