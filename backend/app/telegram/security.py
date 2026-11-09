"""app/telegram/security.py — Telegram admin access control and security audit logging.

Only requests originating from TELEGRAM_ADMIN_CHAT_ID are authorized.
Any message or callback from other chats is ignored and logged as an unauthorized attempt.
"""

from __future__ import annotations

from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.audit import record_audit_log
from app.core.logging import get_logger

log = get_logger(__name__)


async def is_authorized_admin_chat(
    chat_id: int | str,
    session: AsyncSession | None = None,
    admin_chat_id: str | None = None,
    action_attempted: str = "telegram_access",
) -> bool:
    """Verify that chat_id strictly matches TELEGRAM_ADMIN_CHAT_ID.

    If unauthorized:
    - Logs a warning in structured logs.
    - Records an audit log entry in the database (if session is provided).
    - Returns False.
    """
    configured_admin_id = str(admin_chat_id or settings.TELEGRAM_ADMIN_CHAT_ID).strip()
    sender_id = str(chat_id).strip()

    if not configured_admin_id or sender_id != configured_admin_id:
        log.warning(
            "Unauthorized Telegram interaction ignored",
            sender_chat_id=sender_id,
            action_attempted=action_attempted,
        )
        if session:
            try:
                await record_audit_log(
                    session,
                    actor=f"telegram:{sender_id}",
                    action="unauthorized_telegram_access",
                    entity="telegram",
                    entity_id=sender_id,
                    detail={"attempted_action": action_attempted},
                )
            except Exception as exc:
                log.error("Failed to record unauthorized Telegram audit log", error=str(exc))
        return False

    return True
