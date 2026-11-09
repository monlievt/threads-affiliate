"""app/telegram/service.py — Telegram bot service and alert dispatcher."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.logging import get_logger
from app.db.models import Draft
from app.telegram.formatter import format_critical_alert, format_draft_card

log = get_logger(__name__)


@dataclass
class HandlerResponse:
    text: str
    buttons: list[list[dict[str, str]]] | None = None
    already_processed: bool = False



class TelegramBotService:
    """Service for interacting with Telegram Bot API and dispatching alerts."""

    def __init__(
        self,
        bot_token: str | None = None,
        admin_chat_id: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self.admin_chat_id = admin_chat_id or settings.TELEGRAM_ADMIN_CHAT_ID
        self._http_client = http_client

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token.strip() and self.admin_chat_id.strip())

    async def send_message(
        self,
        text: str,
        chat_id: str | int | None = None,
        buttons: list[list[dict[str, str]]] | None = None,
        parse_mode: str = "HTML",
    ) -> bool:
        """Send message to Telegram chat via Bot API."""
        target_chat = str(chat_id or self.admin_chat_id).strip()
        if not self.is_configured or not target_chat:
            log.info("Telegram notification skipped: bot token or chat ID not configured", text_preview=text[:60])
            return False

        payload: dict[str, Any] = {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": parse_mode,
        }

        if buttons:
            payload["reply_markup"] = {
                "inline_keyboard": [
                    [{"text": b["text"], "callback_data": b["callback_data"]} for b in row]
                    for row in buttons
                ]
            }

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

        try:
            if self._http_client:
                resp = await self._http_client.post(url, json=payload, timeout=10.0)
            else:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(url, json=payload, timeout=10.0)

            if resp.status_code == 200:
                return True
            else:
                log.warning("Telegram send failed", status_code=resp.status_code, body=resp.text)
                return False
        except Exception as exc:
            log.error("Telegram request exception", error=str(exc))
            return False

    async def send_alert(self, text: str, is_critical: bool = True) -> bool:
        """Dispatch system alert to admin chat. Critical alerts carry 🚨 prefix."""
        msg = format_critical_alert(text) if is_critical else text
        return await self.send_message(msg)

    async def send_draft_card(
        self,
        draft: Draft,
        niche_name: str | None = None,
        style_name: str | None = None,
        similarity_pct: float | None = None,
    ) -> bool:
        """Send interactive draft review card to admin chat."""
        text, buttons = format_draft_card(
            draft=draft,
            niche_name=niche_name,
            style_name=style_name,
            similarity_pct=similarity_pct,
        )
        return await self.send_message(text=text, buttons=buttons)

    async def process_update(
        self,
        update_data: dict[str, Any],
        session: AsyncSession,
    ) -> HandlerResponse:
        """Dispatch incoming update (message or callback_query) to appropriate handler."""
        from app.telegram.handlers import (
            handle_callback,
            handle_pause,
            handle_quota,
            handle_queue,
            handle_report,
            handle_resume,
            handle_start,
            handle_status,
        )

        # 1. Callback Query
        if "callback_query" in update_data:
            cb = update_data["callback_query"]
            chat_id = cb.get("from", {}).get("id") or cb.get("message", {}).get("chat", {}).get("id")
            callback_data = cb.get("data", "")
            return await handle_callback(chat_id, callback_data, session)

        # 2. Text Message
        if "message" in update_data:
            msg = update_data["message"]
            chat_id = msg.get("chat", {}).get("id")
            raw_text = msg.get("text", "").strip()

            if not raw_text:
                return HandlerResponse(text="Empty message ignored.")

            parts = raw_text.split(maxsplit=1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""

            # Route commands
            if cmd == "/start":
                return await handle_start(chat_id, session)
            elif cmd == "/status":
                return await handle_status(chat_id, session)
            elif cmd == "/queue":
                return await handle_queue(chat_id, session)
            elif cmd == "/pause":
                return await handle_pause(chat_id, session)
            elif cmd == "/resume":
                return await handle_resume(chat_id, args, session)
            elif cmd == "/quota":
                return await handle_quota(chat_id, session)
            elif cmd == "/report":
                return await handle_report(chat_id, session)
            else:
                return HandlerResponse(text=f"Unknown command: {cmd}. Type /start for available commands.")

        return HandlerResponse(text="Unsupported update type.")


# Global helper for quick alerting from any module
async def send_telegram_alert(text: str, is_critical: bool = True) -> bool:
    """Global helper to dispatch Telegram alerts safely."""
    service = TelegramBotService()
    return await service.send_alert(text=text, is_critical=is_critical)
