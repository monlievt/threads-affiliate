"""app/api/oauth.py — OAuth callback endpoints for Meta Threads integration.

Flow:
1. Admin initiates via GET /api/oauth/threads/authorize
2. Meta redirects to GET /api/oauth/threads/callback with authorization code
3. Code is exchanged for a ~60-day long-lived token
4. Token is encrypted via Fernet before storing in DB accounts table
5. Audit log is recorded; token plaintext is immediately discarded
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.clock import utc_now, utc_now_iso
from app.core.crypto import encrypt_token
from app.core.logging import get_logger
from app.core.security import get_current_admin
from app.db.models import Account
from app.db.session import get_db
from app.threads.oauth import exchange_code_for_token, get_authorization_url

logger = get_logger(__name__)

router = APIRouter(prefix="/api/oauth/threads", tags=["oauth"])


@router.get("/authorize")
async def get_threads_auth_url(
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> dict[str, str]:
    """Generate Meta Threads authorization URL for connecting account."""
    url = get_authorization_url()
    return {"authorization_url": url}


@router.get("/callback")
async def threads_oauth_callback(
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Handle Meta OAuth callback, exchange code, encrypt token, and store account in DB."""
    if error:
        logger.error("Threads OAuth error received", error=error, description=error_description)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth authorization failed: {error} — {error_description}",
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code in OAuth callback",
        )

    try:
        # Exchange code for long-lived token (~60 days)
        token_info, user_id = await exchange_code_for_token(code)
    except Exception as exc:
        logger.error("Failed to complete Threads OAuth handshake", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Threads OAuth handshake failed: {exc}",
        ) from exc

    # Encrypt token before persisting
    encrypted_bytes = encrypt_token(token_info.access_token)
    expires_at = (utc_now() + timedelta(seconds=token_info.expires_in)).isoformat()
    now_iso = utc_now_iso()

    # Find existing account or create new one
    account = await session.scalar(
        select(Account).where(Account.threads_user_id == user_id)
    )

    if account:
        account.token_encrypted = encrypted_bytes
        account.token_expires_at = expires_at
        account.connected_at = now_iso
        account.updated_at = now_iso
    else:
        account = Account(
            threads_user_id=user_id,
            token_encrypted=encrypted_bytes,
            token_expires_at=expires_at,
            connected_at=now_iso,
            country_code="US",
            timezone="America/New_York",
            automation_mode="manual_approve",
            created_at=now_iso,
            updated_at=now_iso,
        )
        session.add(account)

    await session.commit()
    await session.refresh(account)

    # Record audit log without sensitive token
    await record_audit(
        session,
        actor="admin",
        action="threads_oauth_connected",
        entity="accounts",
        entity_id=account.id,
        detail={
            "threads_user_id": user_id,
            "expires_in_days": token_info.expires_in // 86400,
        },
    )

    logger.info("Threads account successfully connected and token encrypted", threads_user_id=user_id)

    return {
        "status": "ok",
        "message": "Threads account connected successfully",
        "account_id": account.id,
        "threads_user_id": user_id,
        "expires_at": expires_at,
    }
