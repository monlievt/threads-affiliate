"""tests/test_telegram_bot.py — Comprehensive test suite for Telegram Bot (T-020).

Verifies:
1. Admin-only security: foreign/unauthorized chats are ignored and recorded in audit log.
2. Idempotency: double-clicks on callback buttons do NOT duplicate or corrupt state.
3. Commands: /start, /status, /queue, /pause, /resume (with confirmation), /quota, /report.
4. Card formatting and callback data structure: draft:{id}:{action}:{version}.
5. Alert dispatcher with critical 🚨 prefix.
"""

from __future__ import annotations

import json
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.audit import get_recent_audit_logs
from app.db.models import Account, Draft, Niche, Style, utc_now_iso
from app.safety.killswitch import is_kill_switch_active, set_kill_switch
from app.telegram.formatter import format_critical_alert, format_draft_card
from app.telegram.handlers import (
    handle_callback,
    handle_pause,
    handle_queue,
    handle_quota,
    handle_report,
    handle_resume,
    handle_start,
    handle_status,
)
from app.telegram.security import is_authorized_admin_chat
from app.telegram.service import TelegramBotService


ADMIN_CHAT_ID = "123456789"
STRANGER_CHAT_ID = "999888777"


@pytest.fixture(autouse=True)
def setup_telegram_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "TELEGRAM_ADMIN_CHAT_ID", ADMIN_CHAT_ID)
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "fake-test-bot-token")


# ---------------------------------------------------------------------------
# 1. Security: Admin-only Check & Audit Recording
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_only_security_and_audit(db_session: AsyncSession) -> None:
    # 1. Authorized chat
    is_admin = await is_authorized_admin_chat(ADMIN_CHAT_ID, db_session)
    assert is_admin is True

    # 2. Foreign / unauthorized chat
    is_stranger = await is_authorized_admin_chat(
        STRANGER_CHAT_ID,
        db_session,
        action_attempted="/status",
    )
    assert is_stranger is False

    # Verify audit log recorded the security event
    logs = await get_recent_audit_logs(db_session, limit=10, action="unauthorized_telegram_access")
    assert len(logs) >= 1
    assert logs[0].actor == f"telegram:{STRANGER_CHAT_ID}"
    assert logs[0].entity == "telegram"


# ---------------------------------------------------------------------------
# 2. Draft Card Formatter & Spec Compliance
# ---------------------------------------------------------------------------
def test_draft_card_formatter() -> None:
    draft = Draft(
        id="abc12345-6789-0000-0000-111122223333",
        account_id="acc-1",
        prompt_version="p_v1",
        llm_model="gemini-2.5-pro",
        parts=json.dumps([{"part_index": 1, "text": "Check out this compact silicone colander!"}]),
        link_url="https://benable.com/kitchen/clip",
        status="pending_review",
        text_hash="hash123",
        scheduled_at="2026-11-09T14:30:00Z",
    )

    text, buttons = format_draft_card(
        draft=draft,
        niche_name="Kitchen Hacks",
        style_name="curator",
        slot_label="14:30 EST",
        similarity_pct=41.2,
        version="v1",
    )

    # Assert required spec markers
    assert "📝 <b>Draft #abc12345</b>" in text
    assert "Niche: Kitchen Hacks" in text
    assert "Style: curator" in text
    assert "Slot: 14:30 EST" in text
    assert "Check out this compact silicone colander!" in text
    assert "https://benable.com/kitchen/clip" in text
    assert "Validator: ✅ semua lolos" in text
    assert "Mirip terdekat: 41%" in text

    # Assert inline keyboard buttons structure
    assert len(buttons) == 2
    row1 = buttons[0]
    assert row1[0]["text"] == "✅ Setujui"
    assert row1[0]["callback_data"] == f"draft:{draft.id}:approve:v1"
    assert row1[1]["text"] == "❌ Tolak"
    assert row1[1]["callback_data"] == f"draft:{draft.id}:reject:v1"

    row2 = buttons[1]
    assert row2[0]["text"] == "🔁 Regenerasi"
    assert row2[0]["callback_data"] == f"draft:{draft.id}:regenerate:v1"


# ---------------------------------------------------------------------------
# 3. Commands: /start, /status, /queue, /quota, /report
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_telegram_commands(db_session: AsyncSession) -> None:
    # 1. /start
    resp_start = await handle_start(ADMIN_CHAT_ID, db_session)
    assert "/status" in resp_start.text
    assert "/pause" in resp_start.text

    # Stranger blocked
    resp_unauth = await handle_start(STRANGER_CHAT_ID, db_session)
    assert "Unauthorized" in resp_unauth.text

    # 2. /status
    resp_status = await handle_status(ADMIN_CHAT_ID, db_session)
    assert "System Status" in resp_status.text
    assert "Kill Switch" in resp_status.text

    # 3. /queue when empty
    resp_queue_empty = await handle_queue(ADMIN_CHAT_ID, db_session)
    assert "Tidak ada draf yang menunggu review" in resp_queue_empty.text

    # 4. /queue with pending draft
    niche = Niche(name="Coffee", status="active")
    style = Style(name="quick_review", description="Brief review", tone_rules="Concise", max_chars=300)
    db_session.add_all([niche, style])
    await db_session.commit()

    draft = Draft(
        account_id="acc-1",
        niche_id=niche.id,
        style_id=style.id,
        prompt_version="p_v1",
        llm_model="gemini-2.5-pro",
        parts=json.dumps([{"text": "Best manual coffee grinder under $0? No prices!"}]),
        status="pending_review",
        text_hash="coffee-hash-1",
    )
    db_session.add(draft)
    await db_session.commit()

    resp_queue = await handle_queue(ADMIN_CHAT_ID, db_session)
    assert "📝 <b>Draft #" in resp_queue.text
    assert resp_queue.buttons is not None

    # 5. /quota
    resp_quota = await handle_quota(ADMIN_CHAT_ID, db_session)
    assert "Daily Quota & Budget" in resp_quota.text

    # 6. /report
    resp_report = await handle_report(ADMIN_CHAT_ID, db_session)
    assert "Daily Report" in resp_report.text


# ---------------------------------------------------------------------------
# 4. Commands: /pause and /resume (with confirmation)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_telegram_pause_and_resume_flow(db_session: AsyncSession) -> None:
    # Initially disarm kill switch
    await set_kill_switch(db_session, active=False, reason="Prep test", actor="test")
    assert await is_kill_switch_active(db_session) is False

    # 1. /pause engages kill switch
    pause_resp = await handle_pause(ADMIN_CHAT_ID, db_session)
    assert "KILL SWITCH ENGAGED (ON)" in pause_resp.text
    assert await is_kill_switch_active(db_session) is True

    # 2. /resume without confirmation prompts operator
    prompt_resp = await handle_resume(ADMIN_CHAT_ID, "", db_session)
    assert "Konfirmasi Pengaktifan Kembali" in prompt_resp.text
    assert prompt_resp.buttons is not None
    # Kill switch MUST still remain active!
    assert await is_kill_switch_active(db_session) is True

    # 3. /resume confirm disarms kill switch
    confirm_resp = await handle_resume(ADMIN_CHAT_ID, "confirm", db_session)
    assert "KILL SWITCH DISARMED (OFF)" in confirm_resp.text
    assert await is_kill_switch_active(db_session) is False


# ---------------------------------------------------------------------------
# 5. Idempotency: Double clicks do NOT duplicate action
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_callback_idempotency_double_click(db_session: AsyncSession) -> None:
    draft = Draft(
        account_id="acc-1",
        prompt_version="p_v1",
        llm_model="gemini-2.5-pro",
        parts=json.dumps([{"text": "Sample draft for review"}]),
        status="pending_review",
        text_hash="idemp-hash-1",
    )
    db_session.add(draft)
    await db_session.commit()
    await db_session.refresh(draft)

    # --- Click 1: Approve ---
    cb1 = await handle_callback(
        ADMIN_CHAT_ID,
        f"draft:{draft.id}:approve:v1",
        db_session,
    )
    assert cb1.already_processed is False
    assert "disetujui" in cb1.text.lower()

    # Verify status changed to approved
    await db_session.refresh(draft)
    assert draft.status == "approved"
    assert draft.reviewed_at is not None

    # --- Click 2: Duplicate Approve (Simulating double-tap / slow connection) ---
    cb2 = await handle_callback(
        ADMIN_CHAT_ID,
        f"draft:{draft.id}:approve:v1",
        db_session,
    )
    assert cb2.already_processed is True
    assert "sudah disetujui" in cb2.text.lower()
    assert "tidak ada aksi ganda" in cb2.text.lower()

    # --- Click 3: Reject on already approved draft ---
    cb3 = await handle_callback(
        ADMIN_CHAT_ID,
        f"draft:{draft.id}:reject:v1",
        db_session,
    )
    # Draft is already approved; cannot reject without resetting state
    await db_session.refresh(draft)
    assert draft.status == "approved"

    # Verify audit logs: only 1 approve log recorded for this draft
    logs = await get_recent_audit_logs(db_session, limit=20, action="approve_telegram")
    draft_logs = [l for l in logs if l.entity_id == draft.id]
    assert len(draft_logs) == 1


# ---------------------------------------------------------------------------
# 6. Service & Update Processor
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_telegram_service_update_processing(db_session: AsyncSession) -> None:
    service = TelegramBotService()

    # Process command update
    cmd_update = {
        "message": {
            "chat": {"id": int(ADMIN_CHAT_ID)},
            "text": "/status",
        }
    }
    resp = await service.process_update(cmd_update, db_session)
    assert "System Status" in resp.text

    # Process callback query update
    draft = Draft(
        account_id="acc-1",
        prompt_version="p_v1",
        llm_model="gemini-2.5-pro",
        parts=json.dumps([{"text": "Sample draft to reject"}]),
        status="pending_review",
        text_hash="reject-hash-1",
    )
    db_session.add(draft)
    await db_session.commit()
    await db_session.refresh(draft)

    cb_update = {
        "callback_query": {
            "from": {"id": int(ADMIN_CHAT_ID)},
            "data": f"draft:{draft.id}:reject:v1",
        }
    }
    resp_cb = await service.process_update(cb_update, db_session)
    assert "ditolak" in resp_cb.text.lower()

    await db_session.refresh(draft)
    assert draft.status == "rejected"


def test_critical_alert_formatting() -> None:
    alert = format_critical_alert("Publisher failed with 500 server error")
    assert alert.startswith("🚨 <b>SYSTEM ALERT</b>")
    assert "Publisher failed" in alert
