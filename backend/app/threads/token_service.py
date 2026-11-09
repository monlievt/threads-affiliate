"""app/threads/token_service.py — Token lifecycle management, automatic refresh, and failure alerting.

Hard Rules (docs/03 §4.C, docs/05 §1.2, docs/06 §3):
1. Proactive refresh: Long-lived tokens (~60 days) must be refreshed when < 15 days remain.
2. Encrypted storage: Access tokens are always encrypted in database (Fernet).
3. Fail-closed: If token refresh fails, immediately engage emergency kill switch (active=True), record critical incident, and dispatch Telegram alert.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_log
from app.core.clock import utc_now, utc_now_iso
from app.core.crypto import decrypt_token, encrypt_token
from app.core.logging import get_logger
from app.db.models import Account, Incident
from app.safety.killswitch import set_kill_switch
from app.telegram.service import send_telegram_alert
from app.threads.base import ThreadsClientProtocol, TokenInfo
from app.threads.client import ThreadsHttpClient

logger = get_logger(__name__)

DEFAULT_REFRESH_THRESHOLD_DAYS = 15


def get_token_status(
    account: Account,
    now: datetime | None = None,
    threshold_days: int = DEFAULT_REFRESH_THRESHOLD_DAYS,
) -> dict[str, Any]:
    """Calculate token validity and determine if renewal is needed.

    Returns:
        dict with keys: has_token, valid, days_remaining, needs_refresh, expires_at
    """
    if not account.token_encrypted:
        return {
            "has_token": False,
            "valid": False,
            "days_remaining": 0.0,
            "needs_refresh": True,
            "expires_at": None,
        }

    if not account.token_expires_at:
        return {
            "has_token": True,
            "valid": False,
            "days_remaining": 0.0,
            "needs_refresh": True,
            "expires_at": None,
        }

    now_utc = now or utc_now()
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    try:
        expires_dt = datetime.fromisoformat(account.token_expires_at.replace("Z", "+00:00"))
        if expires_dt.tzinfo is None:
            expires_dt = expires_dt.replace(tzinfo=timezone.utc)

        remaining_seconds = (expires_dt - now_utc).total_seconds()
        days_remaining = max(0.0, remaining_seconds / 86400.0)
        valid = remaining_seconds > 0
        needs_refresh = (not valid) or (days_remaining < threshold_days)

        return {
            "has_token": True,
            "valid": valid,
            "days_remaining": round(days_remaining, 2),
            "needs_refresh": needs_refresh,
            "expires_at": account.token_expires_at,
        }
    except Exception as exc:
        logger.warning("Could not parse account token_expires_at", error=str(exc))
        return {
            "has_token": True,
            "valid": False,
            "days_remaining": 0.0,
            "needs_refresh": True,
            "expires_at": account.token_expires_at,
        }


async def refresh_account_token(
    session: AsyncSession,
    account: Account,
    client: ThreadsClientProtocol | None = None,
) -> TokenInfo:
    """Refresh the long-lived OAuth access token for an account before it expires.

    If refresh succeeds:
    - Encrypts and updates token_encrypted.
    - Updates token_expires_at.
    - Records audit log entry.

    If refresh fails:
    - Engages emergency kill switch (active=True).
    - Records incident.
    - Dispatches critical Telegram alert.
    - Records audit log entry.
    - Re-raises the exception.
    """
    if not account.token_encrypted:
        err_msg = f"Account @{account.username or account.id} has no encrypted token to refresh."
        logger.error(err_msg)
        await set_kill_switch(session, active=True, reason=err_msg, actor="system")
        await send_telegram_alert(f"🚨 {err_msg} Kill Switch diaktifkan otomatis.")
        raise ValueError(err_msg)

    # Resolve client
    if client is None:
        decrypted_token = decrypt_token(account.token_encrypted)
        client = ThreadsHttpClient(
            user_id=account.threads_user_id or "",
            access_token=decrypted_token,
        )

    try:
        logger.info("Attempting long-lived token refresh", account_id=account.id, username=account.username)
        token_info = await client.refresh_token()

        now = utc_now()
        new_expires_dt = now + timedelta(seconds=token_info.expires_in)
        new_expires_iso = new_expires_dt.isoformat()

        # Update Account in database
        account.token_encrypted = encrypt_token(token_info.access_token)
        account.token_expires_at = new_expires_iso
        account.updated_at = utc_now_iso()

        await session.commit()
        await session.refresh(account)

        # Record Audit Log
        await record_audit_log(
            session,
            actor="token_refresher",
            action="token_refreshed",
            entity="accounts",
            entity_id=account.id,
            detail={
                "username": account.username,
                "expires_at": new_expires_iso,
                "expires_in_days": round(token_info.expires_in / 86400.0, 1),
            },
        )

        logger.info(
            "Token refreshed successfully",
            account_id=account.id,
            username=account.username,
            expires_at=new_expires_iso,
        )
        return token_info

    except Exception as exc:
        err_detail = f"Token refresh failed for account @{account.username or account.id}: {exc}"
        logger.critical(err_detail, error=str(exc))

        # Fail-closed: engage emergency kill switch immediately!
        await set_kill_switch(
            session,
            active=True,
            reason=err_detail,
            actor="system",
        )

        # Record critical incident
        incident = Incident(
            severity="critical",
            code="TOKEN_REFRESH_FAILED",
            detail=err_detail,
        )
        session.add(incident)
        await session.commit()

        # Alert admin on Telegram
        await send_telegram_alert(
            f"🚨 <b>TOKEN REFRESH FAILED</b>\n\n"
            f"Akun: @{account.username or account.id}\n"
            f"Galat: <code>{exc}</code>\n\n"
            f"Kill Switch telah diaktifkan otomatis. Perlu re-autentikasi akun di dashboard sebelum publishing dapat dilanjutkan."
        )

        await record_audit_log(
            session,
            actor="token_refresher",
            action="token_refresh_failed",
            entity="accounts",
            entity_id=account.id,
            detail={"error": str(exc)},
        )

        raise


async def check_and_refresh_all_accounts(
    session: AsyncSession,
    client_factory: Callable[[Account], ThreadsClientProtocol] | None = None,
    threshold_days: int = DEFAULT_REFRESH_THRESHOLD_DAYS,
) -> dict[str, Any]:
    """Check all registered accounts and refresh tokens that are near expiration."""
    query = select(Account).where(Account.token_encrypted.isnot(None))
    result = await session.execute(query)
    accounts = result.scalars().all()

    total_checked = len(accounts)
    refreshed_count = 0
    failed_count = 0
    errors: list[dict[str, str]] = []

    for acc in accounts:
        status = get_token_status(acc, threshold_days=threshold_days)
        if status["needs_refresh"]:
            client = client_factory(acc) if client_factory else None
            try:
                await refresh_account_token(session, acc, client=client)
                refreshed_count += 1
            except Exception as exc:
                failed_count += 1
                errors.append({"account_id": acc.id, "error": str(exc)})

    return {
        "total_checked": total_checked,
        "refreshed_count": refreshed_count,
        "failed_count": failed_count,
        "errors": errors,
    }
