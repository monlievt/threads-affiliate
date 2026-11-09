"""app/telegram/bot.py — Telegram bot runner and long-polling worker."""

from __future__ import annotations

import asyncio
from typing import Any

from app.config import settings
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
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
from app.telegram.security import is_authorized_admin_chat

log = get_logger(__name__)


def build_telegram_application() -> Any:
    """Build python-telegram-bot Application if library is installed."""
    try:
        from telegram import Update
        from telegram.ext import (
            Application,
            CallbackQueryHandler,
            CommandHandler,
            ContextTypes,
        )
    except ImportError:
        log.warning("python-telegram-bot is not installed. Polling worker cannot start directly.")
        return None

    if not settings.TELEGRAM_BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN is not configured.")
        return None

    async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat or not update.message:
            return
        async with AsyncSessionLocal() as session:
            resp = await handle_start(update.effective_chat.id, session)
            await update.message.reply_html(resp.text)

    async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat or not update.message:
            return
        async with AsyncSessionLocal() as session:
            resp = await handle_status(update.effective_chat.id, session)
            await update.message.reply_html(resp.text)

    async def queue_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat or not update.message:
            return
        async with AsyncSessionLocal() as session:
            resp = await handle_queue(update.effective_chat.id, session)
            reply_markup = None
            if resp.buttons:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup

                keyboard = [
                    [InlineKeyboardButton(b["text"], callback_data=b["callback_data"]) for b in row]
                    for row in resp.buttons
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_html(resp.text, reply_markup=reply_markup)

    async def pause_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat or not update.message:
            return
        async with AsyncSessionLocal() as session:
            resp = await handle_pause(update.effective_chat.id, session)
            await update.message.reply_html(resp.text)

    async def resume_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat or not update.message:
            return
        args = " ".join(context.args) if context.args else ""
        async with AsyncSessionLocal() as session:
            resp = await handle_resume(update.effective_chat.id, args, session)
            reply_markup = None
            if resp.buttons:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup

                keyboard = [
                    [InlineKeyboardButton(b["text"], callback_data=b["callback_data"]) for b in row]
                    for row in resp.buttons
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_html(resp.text, reply_markup=reply_markup)

    async def quota_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat or not update.message:
            return
        async with AsyncSessionLocal() as session:
            resp = await handle_quota(update.effective_chat.id, session)
            await update.message.reply_html(resp.text)

    async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat or not update.message:
            return
        async with AsyncSessionLocal() as session:
            resp = await handle_report(update.effective_chat.id, session)
            await update.message.reply_html(resp.text)

    async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.data or not update.effective_chat:
            return
        await query.answer()
        async with AsyncSessionLocal() as session:
            resp = await handle_callback(update.effective_chat.id, query.data, session)
            await query.edit_message_text(resp.text, parse_mode="HTML")

    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("queue", queue_cmd))
    app.add_handler(CommandHandler("pause", pause_cmd))
    app.add_handler(CommandHandler("resume", resume_cmd))
    app.add_handler(CommandHandler("quota", quota_cmd))
    app.add_handler(CommandHandler("report", report_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))

    return app


async def run_bot_polling() -> None:
    """Run bot polling loop."""
    app = build_telegram_application()
    if not app:
        log.warning("Telegram bot polling not started (missing library or token)")
        return

    log.info("Starting Telegram bot long-polling...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
