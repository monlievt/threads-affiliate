"""app/safety/minimal_guard.py — Minimal publish guard for manual test scripts and initial publish gate.

Checks:
1. Kill switch OFF? (Fail-closed: if ON -> block with KILL_SWITCH_ON)
2. Token valid and decryptable?
3. Text length valid (1 <= len <= 500 characters)?
4. Idempotency: Has this draft already been published?
"""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_token
from app.db.models import Account, Post
from app.safety.killswitch import is_kill_switch_active


class GuardDecision(BaseModel):
    """Result of a guard check."""

    allowed: bool
    reason: str | None = None
    retry_after: datetime | None = None


async def check_minimal_guard(
    session: AsyncSession,
    *,
    account: Account,
    text: str,
    draft_id: str | None = None,
) -> GuardDecision:
    """Perform minimal guard validation before any publish operation.

    Args:
        session: Active async DB session.
        account: Account record intending to publish.
        text: Post content text.
        draft_id: Optional draft ID to check idempotency against.

    Returns:
        GuardDecision with allowed=True if all checks pass; allowed=False + reason otherwise.
    """
    # 1. Kill switch check
    if await is_kill_switch_active(session):
        return GuardDecision(
            allowed=False,
            reason="KILL_SWITCH_ON: Publishing is blocked by global emergency kill switch.",
        )

    # 2. Token validity check
    if not account.token_encrypted:
        return GuardDecision(
            allowed=False,
            reason="TOKEN_MISSING: Account has no encrypted Threads token.",
        )

    try:
        decrypted = decrypt_token(account.token_encrypted)
        if not decrypted:
            return GuardDecision(
                allowed=False,
                reason="TOKEN_EMPTY: Decrypted token is empty.",
            )
    except Exception as exc:
        return GuardDecision(
            allowed=False,
            reason=f"TOKEN_DECRYPTION_FAILED: {exc}",
        )

    # 3. Text length validation
    text_len = len(text.strip())
    if text_len == 0:
        return GuardDecision(
            allowed=False,
            reason="TEXT_EMPTY: Post text cannot be empty.",
        )
    if text_len > 500:
        return GuardDecision(
            allowed=False,
            reason=f"TEXT_LENGTH_EXCEEDED: Post text is {text_len} characters (max allowed is 500).",
        )

    # 4. Idempotency check: has this draft already been published?
    if draft_id:
        existing_post = await session.scalar(
            select(Post).where(Post.draft_id == draft_id)
        )
        if existing_post:
            return GuardDecision(
                allowed=False,
                reason=f"ALREADY_PUBLISHED: Draft {draft_id} has already been published as post {existing_post.id}.",
            )

    return GuardDecision(allowed=True)
