"""app/threads/publisher.py — Safe single post publishing through guard.

Enforces:
- PublishGuard check (fail closed)
- Creation ID recording for crash reconciliation
- Idempotency via unique posts.draft_id constraint
- Audit logging of every publication
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.clock import utc_now_iso
from app.core.crypto import decrypt_token
from app.core.logging import get_logger
from app.db.models import Account, Draft, Post
from app.safety.minimal_guard import check_minimal_guard
from app.threads.base import ThreadsClientProtocol
from app.threads.client import ThreadsHttpClient

logger = get_logger(__name__)


def compute_text_hash(text: str) -> str:
    """Compute normalized SHA-256 hash for draft deduplication."""
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def publish_single_post(
    session: AsyncSession,
    *,
    account_id: str,
    text: str,
    draft_id: str | None = None,
    client: ThreadsClientProtocol | None = None,
    actor: str = "manual_script",
) -> Post:
    """Safely publish a single post to Threads through minimal guard verification.

    Args:
        session: Active async database session.
        account_id: Target account ID.
        text: Text content to post (<= 500 characters).
        draft_id: Optional existing draft ID; if None, a new draft record is created.
        client: Optional injected Threads client (e.g. FakeThreadsClient for testing).
        actor: Identity of who triggered the publication ('admin', 'manual_script', etc.).

    Returns:
        The newly created Post record.

    Raises:
        PermissionError: If blocked by PublishGuard (e.g., kill switch engaged).
        ValueError: If account not found or API parameters invalid.
    """
    # 1. Fetch account
    account = await session.scalar(select(Account).where(Account.id == account_id))
    if not account:
        raise ValueError(f"Account with ID {account_id!r} not found.")

    # 2. Minimal guard check
    decision = await check_minimal_guard(
        session,
        account=account,
        text=text,
        draft_id=draft_id,
    )
    if not decision.allowed:
        logger.warning(
            "Publish blocked by guard",
            account_id=account_id,
            reason=decision.reason,
        )
        raise PermissionError(f"Publish blocked: {decision.reason}")

    # 3. Resolve or create Draft record
    now_iso = utc_now_iso()
    text_hash = compute_text_hash(text)

    if draft_id:
        draft = await session.scalar(select(Draft).where(Draft.id == draft_id))
        if not draft:
            raise ValueError(f"Draft with ID {draft_id!r} not found.")
        draft.status = "publishing"
        draft.updated_at = now_iso
    else:
        draft = Draft(
            account_id=account.id,
            kind="post",
            prompt_version="manual_test",
            llm_model="none",
            parts=json.dumps([text]),
            text_hash=text_hash,
            status="publishing",
            created_at=now_iso,
            updated_at=now_iso,
        )
        session.add(draft)

    await session.commit()
    await session.refresh(draft)

    # 4. Resolve client
    if client is None:
        decrypted_token = decrypt_token(account.token_encrypted or b"")
        user_id = account.threads_user_id or ""
        client = ThreadsHttpClient(user_id=user_id, access_token=decrypted_token)

    # 5. Step 1: Create container
    logger.info("Creating Threads media container", draft_id=draft.id)
    creation_id = await client.create_text_container(text)

    # 6. Step 2: Publish container
    logger.info("Publishing Threads media container", creation_id=creation_id, draft_id=draft.id)
    published = await client.publish(creation_id)

    # 7. Record Post
    published_at = utc_now_iso()
    post = Post(
        draft_id=draft.id,
        account_id=account.id,
        threads_media_id=published.media_id,
        permalink=published.permalink,
        creation_id=creation_id,
        published_at=published_at,
        created_at=published_at,
    )
    draft.status = "published"
    draft.updated_at = published_at

    session.add(post)
    await session.commit()
    await session.refresh(post)

    # 8. Record Audit Log
    await record_audit(
        session,
        actor=actor,
        action="post_published",
        entity="posts",
        entity_id=post.id,
        detail={
            "threads_media_id": published.media_id,
            "permalink": published.permalink,
            "draft_id": draft.id,
            "creation_id": creation_id,
        },
    )

    logger.info(
        "Post published successfully",
        post_id=post.id,
        threads_media_id=published.media_id,
        permalink=published.permalink,
    )

    return post

