"""app/threads/publisher.py — Idempotent post publisher, crash reconciliation, and retry manager.

Strict Safety Controls (from docs/05 §1.4, docs/06 §3, AGENTS.md):
1. Comprehensive PublishGuard verification (fail-closed, no bypass parameter).
2. Idempotency: Drafts already published return the existing post record; no duplicate publishing.
3. Crash reconciliation: Container creation ID recorded in system_state; hanging publishing drafts recovered safely.
4. Non-retryable 4xx errors: Mark draft as 'failed_permanent' and never retry.
5. Consecutive error threshold: 2 consecutive publish failures engage the emergency kill switch automatically and alert admin.
6. Rate limit (429): Immediately engages the kill switch and halts further attempts.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_log
from app.core.clock import utc_now, utc_now_iso
from app.core.crypto import decrypt_token
from app.core.logging import get_logger
from app.db.models import Account, Draft, Post, SystemState
from app.safety.guard import PublishGuard
from app.safety.killswitch import set_kill_switch
from app.telegram.service import send_telegram_alert
from app.threads.base import ThreadsClientProtocol
from app.threads.client import (
    ThreadsApiError,
    ThreadsHttpClient,
    ThreadsPermanentApiError,
    ThreadsRateLimitError,
)

logger = get_logger(__name__)

CONSECUTIVE_ERRORS_KEY = "consecutive_publish_errors"
CREATION_ID_PREFIX = "draft_creation_id:"


def compute_text_hash(text: str) -> str:
    """Compute normalized SHA-256 hash for draft deduplication."""
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Error Tracking & Auto Kill-Switch
# ---------------------------------------------------------------------------
async def get_consecutive_publish_errors(session: AsyncSession) -> int:
    """Retrieve the number of consecutive publish errors from system_state."""
    record = await session.scalar(
        select(SystemState).where(SystemState.key == CONSECUTIVE_ERRORS_KEY)
    )
    if record is None or not record.value:
        return 0
    try:
        return int(record.value.strip())
    except ValueError:
        return 0


async def increment_consecutive_publish_errors(session: AsyncSession) -> int:
    """Increment consecutive publish error counter and return new count."""
    current = await get_consecutive_publish_errors(session)
    new_count = current + 1
    now_iso = utc_now_iso()

    record = await session.scalar(
        select(SystemState).where(SystemState.key == CONSECUTIVE_ERRORS_KEY)
    )
    if record is None:
        session.add(
            SystemState(
                key=CONSECUTIVE_ERRORS_KEY,
                value=str(new_count),
                updated_at=now_iso,
            )
        )
    else:
        record.value = str(new_count)
        record.updated_at = now_iso

    await session.commit()
    logger.warning("Consecutive publish errors incremented", count=new_count)
    return new_count


async def reset_consecutive_publish_errors(session: AsyncSession) -> None:
    """Reset consecutive publish error counter to 0 upon successful publication."""
    now_iso = utc_now_iso()
    record = await session.scalar(
        select(SystemState).where(SystemState.key == CONSECUTIVE_ERRORS_KEY)
    )
    if record is not None:
        record.value = "0"
        record.updated_at = now_iso
        await session.commit()


# ---------------------------------------------------------------------------
# Crash Recovery Container Caching Helpers
# ---------------------------------------------------------------------------
async def get_saved_creation_id(session: AsyncSession, draft_id: str) -> str | None:
    """Retrieve in-flight creation ID for a draft if step 1 succeeded before a crash."""
    key = f"{CREATION_ID_PREFIX}{draft_id}"
    record = await session.scalar(
        select(SystemState).where(SystemState.key == key)
    )
    return record.value if record and record.value else None


async def save_creation_id(session: AsyncSession, draft_id: str, creation_id: str) -> None:
    """Save creation ID to system_state immediately after container creation."""
    key = f"{CREATION_ID_PREFIX}{draft_id}"
    now_iso = utc_now_iso()
    record = await session.scalar(
        select(SystemState).where(SystemState.key == key)
    )
    if record is None:
        session.add(SystemState(key=key, value=creation_id, updated_at=now_iso))
    else:
        record.value = creation_id
        record.updated_at = now_iso
    await session.commit()


async def clear_saved_creation_id(session: AsyncSession, draft_id: str) -> None:
    """Remove temporary creation ID record once post is published or failed permanently."""
    key = f"{CREATION_ID_PREFIX}{draft_id}"
    record = await session.scalar(
        select(SystemState).where(SystemState.key == key)
    )
    if record is not None:
        await session.delete(record)
        await session.commit()


# ---------------------------------------------------------------------------
# Safe Idempotent Publisher
# ---------------------------------------------------------------------------
async def publish_single_post(
    session: AsyncSession,
    *,
    account_id: str,
    text: str,
    draft_id: str | None = None,
    client: ThreadsClientProtocol | None = None,
    actor: str = "manual_script",
) -> Post:
    """Safely and idempotently publish a single post to Threads through PublishGuard.

    Handles:
    - Idempotency: Returns existing post if draft already published.
    - 4xx client errors: Marks draft as 'failed_permanent' without retry.
    - 429 rate limit or 2 consecutive failures: Engages emergency kill switch and alerts.
    - Crash recovery: Reuses existing container creation_id if step 1 previously succeeded.

    Raises:
        PermissionError: If blocked by PublishGuard.
        ThreadsPermanentApiError: If non-retryable 4xx returned.
        ThreadsApiError: If API call fails after retries.
    """
    now_iso = utc_now_iso()

    # 1. Fetch account
    account = await session.scalar(select(Account).where(Account.id == account_id))
    if not account:
        raise ValueError(f"Account with ID {account_id!r} not found.")

    # 2. Resolve or create Draft
    if draft_id:
        draft = await session.scalar(select(Draft).where(Draft.id == draft_id))
        if not draft:
            raise ValueError(f"Draft with ID {draft_id!r} not found.")

        # Idempotency check 1: Check if Post already created for this draft
        existing_post = await session.scalar(
            select(Post).where(Post.draft_id == draft.id)
        )
        if existing_post:
            logger.info("Draft already published. Returning existing post (idempotent no-op).", draft_id=draft.id)
            if draft.status != "published":
                draft.status = "published"
                await session.commit()
            return existing_post

        # Idempotency check 2: Prevent re-running non-retryable failed_permanent drafts
        if draft.status == "failed_permanent":
            raise ValueError(f"Draft {draft_id!r} has status 'failed_permanent' and cannot be retried.")
    else:
        text_hash = compute_text_hash(text)
        draft = Draft(
            account_id=account.id,
            kind="post",
            prompt_version="manual_test",
            llm_model="none",
            parts=json.dumps([{"text": text}]),
            text_hash=text_hash,
            status="approved",
            created_at=now_iso,
            updated_at=now_iso,
        )
        session.add(draft)
        await session.commit()
        await session.refresh(draft)

    # 3. Comprehensive PublishGuard verification
    decision = await PublishGuard.check(
        session,
        draft=draft,
        account=account,
        client=client,
        check_api_quota=True,
    )
    if not decision.allowed:
        draft.status = "failed"
        draft.reject_reason = decision.reason
        await session.commit()
        logger.warning(
            "Publish blocked by PublishGuard",
            account_id=account_id,
            draft_id=draft.id,
            reason=decision.reason,
        )
        raise PermissionError(f"Publish blocked: {decision.reason}")

    # Mark status as publishing
    draft.status = "publishing"
    draft.updated_at = utc_now_iso()
    await session.commit()

    # 4. Resolve client
    if client is None:
        decrypted_token = decrypt_token(account.token_encrypted or b"")
        user_id = account.threads_user_id or ""
        client = ThreadsHttpClient(user_id=user_id, access_token=decrypted_token)

    # 5. Step 1: Create Container (or reuse from previous crash)
    creation_id = await get_saved_creation_id(session, draft.id)
    if creation_id:
        logger.info("Resuming publish with existing container from crash recovery", creation_id=creation_id, draft_id=draft.id)
    else:
        try:
            logger.info("Creating Threads media container", draft_id=draft.id)
            link_to_attach = draft.link_url if draft.link_placement == "in_post" else None
            creation_id = await client.create_text_container(text, link_attachment=link_to_attach)
            # Save creation_id immediately for crash reconciliation
            await save_creation_id(session, draft.id, creation_id)
        except ThreadsRateLimitError as exc:
            draft.status = "failed"
            draft.reject_reason = "Threads API 429 Rate Limit"
            await session.commit()
            await set_kill_switch(session, active=True, reason="Threads 429 rate limit exceeded", actor="system")
            await send_telegram_alert("🚨 Rate limit 429 dari Threads API. Kill Switch diaktifkan otomatis.")
            raise
        except ThreadsPermanentApiError as exc:
            draft.status = "failed_permanent"
            draft.reject_reason = f"Non-retryable 4xx client error: {exc}"
            await session.commit()
            err_count = await increment_consecutive_publish_errors(session)
            if err_count >= 2:
                await set_kill_switch(session, active=True, reason="Two consecutive publish errors occurred", actor="system")
                await send_telegram_alert("🚨 2 galat publish berturut-turut terdeteksi. Kill Switch diaktifkan otomatis.")
            raise
        except Exception as exc:
            draft.status = "failed"
            draft.reject_reason = f"Failed to create media container: {exc}"
            await session.commit()
            err_count = await increment_consecutive_publish_errors(session)
            if err_count >= 2:
                await set_kill_switch(session, active=True, reason="Two consecutive publish errors occurred", actor="system")
                await send_telegram_alert("🚨 2 galat publish berturut-turut terdeteksi. Kill Switch diaktifkan otomatis.")
            raise

    # 6. Step 2: Publish Container
    try:
        logger.info("Publishing Threads media container", creation_id=creation_id, draft_id=draft.id)
        published = await client.publish(creation_id)
    except ThreadsRateLimitError as exc:
        draft.status = "failed"
        draft.reject_reason = "Threads API 429 Rate Limit during publish"
        await session.commit()
        await set_kill_switch(session, active=True, reason="Threads 429 rate limit exceeded", actor="system")
        await send_telegram_alert("🚨 Rate limit 429 saat mempublikasikan container. Kill Switch diaktifkan otomatis.")
        raise
    except ThreadsPermanentApiError as exc:
        draft.status = "failed_permanent"
        draft.reject_reason = f"Non-retryable 4xx error on publish: {exc}"
        await session.commit()
        await clear_saved_creation_id(session, draft.id)
        err_count = await increment_consecutive_publish_errors(session)
        if err_count >= 2:
            await set_kill_switch(session, active=True, reason="Two consecutive publish errors occurred", actor="system")
            await send_telegram_alert("🚨 2 galat publish berturut-turut terdeteksi. Kill Switch diaktifkan otomatis.")
        raise
    except Exception as exc:
        draft.status = "failed"
        draft.reject_reason = f"Failed to publish container: {exc}"
        await session.commit()
        err_count = await increment_consecutive_publish_errors(session)
        if err_count >= 2:
            await set_kill_switch(session, active=True, reason="Two consecutive publish errors occurred", actor="system")
            await send_telegram_alert("🚨 2 galat publish berturut-turut terdeteksi. Kill Switch diaktifkan otomatis.")
        raise

    # 7. Record Post & Update Status (Atomic success)
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

    # Clean up temporary creation ID
    await clear_saved_creation_id(session, draft.id)

    # Reset consecutive error counter on success!
    await reset_consecutive_publish_errors(session)

    # 8. Record Audit Log
    await record_audit_log(
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


# ---------------------------------------------------------------------------
# Crash Reconciliation
# ---------------------------------------------------------------------------
async def reconcile_in_flight_drafts(
    session: AsyncSession,
    max_stale_seconds: int = 300,
) -> list[str]:
    """Reconcile drafts stuck in 'publishing' state after an unexpected worker crash.

    Cases:
    1. A Post already exists for the draft -> update draft status to 'published'.
    2. No Post exists and draft was last updated > max_stale_seconds ago -> mark 'failed'.
    """
    query = select(Draft).where(Draft.status == "publishing")
    result = await session.execute(query)
    stuck_drafts = result.scalars().all()

    reconciled_ids: list[str] = []
    now = utc_now()

    for draft in stuck_drafts:
        # Check if post was already created before crash
        post = await session.scalar(select(Post).where(Post.draft_id == draft.id))
        if post:
            draft.status = "published"
            draft.updated_at = utc_now_iso()
            await record_audit_log(
                session,
                actor="reconciler",
                action="reconcile_crash_published",
                entity="drafts",
                entity_id=draft.id,
                detail={"post_id": post.id},
            )
            reconciled_ids.append(draft.id)
            continue

        # Check if draft is older than stale threshold
        try:
            updated_dt = datetime.fromisoformat(draft.updated_at.replace("Z", "+00:00"))
            age_sec = (now - updated_dt).total_seconds()
        except Exception:
            age_sec = max_stale_seconds + 1

        if age_sec > max_stale_seconds:
            draft.status = "failed"
            draft.reject_reason = (
                f"Crash reconciliation: publication remained stuck in 'publishing' for {int(age_sec)}s."
            )
            draft.updated_at = utc_now_iso()
            await clear_saved_creation_id(session, draft.id)

            await record_audit_log(
                session,
                actor="reconciler",
                action="reconcile_crash_failed",
                entity="drafts",
                entity_id=draft.id,
                detail={"age_seconds": age_sec},
            )
            reconciled_ids.append(draft.id)

    if reconciled_ids:
        await session.commit()
        logger.info("Reconciled in-flight drafts after crash", count=len(reconciled_ids), ids=reconciled_ids)

    return reconciled_ids
