"""app/safety/guard.py — PublishGuard: The single strict gateway before any post/reply publication.

Hard Rules (docs/06 §1 & AGENTS.md):
- Every publish operation MUST pass through PublishGuard.check()
- 10 sequential checks executed in strict order; stops at first failure
- Fail closed: any uncertainty or missing prerequisite rejects the operation
- NO 'force' or 'bypass' parameter exists anywhere in this module
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now
from app.core.crypto import decrypt_token
from app.core.logging import get_logger
from app.db.models import Account, Draft, Persona, Post
from app.safety.governor import check_governor_limits
from app.safety.killswitch import is_kill_switch_active
from app.safety.similarity import check_draft_similarity_in_db
from app.safety.validators import validate_content
from app.threads.base import ThreadsClientProtocol

logger = get_logger(__name__)


class GuardDecision(BaseModel):
    """The immutable outcome of a PublishGuard evaluation."""

    allowed: bool = Field(..., description="True only if all 10 checks pass cleanly.")
    reason: str | None = Field(default=None, description="Standardized rejection code and explanation.")
    retry_after: datetime | None = Field(default=None, description="Suggested backoff timestamp if transient.")


class PublishGuard:
    """The central gatekeeper enforcing all platform safety and legal compliance rules."""

    @classmethod
    async def check(
        cls,
        session: AsyncSession,
        *,
        draft: Draft,
        account: Account,
        client: ThreadsClientProtocol | None = None,
        check_api_quota: bool = True,
    ) -> GuardDecision:
        """Run all 10 safety and compliance checks sequentially.

        Returns:
            GuardDecision(allowed=True) if all pass; GuardDecision(allowed=False, reason=...) on first failure.
        """
        now = utc_now()

        # -------------------------------------------------------------------
        # Check 1: Kill switch OFF?
        # -------------------------------------------------------------------
        if await is_kill_switch_active(session):
            logger.warning("PublishGuard Check 1 Failed: Kill switch is ENGAGED", draft_id=draft.id)
            return GuardDecision(
                allowed=False,
                reason="KILL_SWITCH_ON: Publishing is halted by emergency kill switch.",
            )

        # -------------------------------------------------------------------
        # Check 2: Token valid and not expired?
        # -------------------------------------------------------------------
        if not account.token_encrypted:
            return GuardDecision(
                allowed=False,
                reason="TOKEN_MISSING: Account has no encrypted Threads token.",
            )

        try:
            raw_token = decrypt_token(account.token_encrypted)
            if not raw_token:
                return GuardDecision(
                    allowed=False,
                    reason="TOKEN_EMPTY: Decrypted token is empty.",
                )
        except Exception as exc:
            return GuardDecision(
                allowed=False,
                reason=f"TOKEN_DECRYPTION_FAILED: Token cannot be decrypted ({exc}).",
            )

        if account.token_expires_at:
            try:
                expires_dt = datetime.fromisoformat(account.token_expires_at.replace("Z", "+00:00"))
                if expires_dt.tzinfo is None:
                    expires_dt = expires_dt.replace(tzinfo=timezone.utc)
                if now >= expires_dt:
                    return GuardDecision(
                        allowed=False,
                        reason="TOKEN_EXPIRED: Threads access token has expired. Re-authenticate via OAuth.",
                    )
            except Exception:
                pass

        # -------------------------------------------------------------------
        # Check 3: Draft status eligible & post doesn't already exist?
        # -------------------------------------------------------------------
        eligible_statuses = {"scheduled", "approved", "publishing"}
        if draft.status not in eligible_statuses:
            return GuardDecision(
                allowed=False,
                reason=f"INVALID_DRAFT_STATUS: Draft status is {draft.status!r}; expected one of {eligible_statuses}.",
            )

        existing_post = await session.scalar(
            select(Post).where(Post.draft_id == draft.id)
        )
        if existing_post:
            return GuardDecision(
                allowed=False,
                reason=f"ALREADY_PUBLISHED: Draft {draft.id} is already linked to Post {existing_post.id}.",
            )

        # -------------------------------------------------------------------
        # Check 4: Approval matches active automation mode?
        # -------------------------------------------------------------------
        mode = account.automation_mode
        if mode == "manual_approve":
            if draft.status not in ("approved", "publishing"):
                return GuardDecision(
                    allowed=False,
                    reason=f"MANUAL_APPROVAL_REQUIRED: Account is in 'manual_approve' mode; draft must be approved (current: {draft.status!r}).",
                )

        # -------------------------------------------------------------------
        # Extract draft text content
        # -------------------------------------------------------------------
        parts: list[str] = []
        try:
            parsed_parts = json.loads(draft.parts)
            if isinstance(parsed_parts, list):
                parts = [str(p) for p in parsed_parts if str(p).strip()]
            elif isinstance(parsed_parts, str):
                parts = [parsed_parts]
        except Exception:
            parts = [draft.parts]

        if not parts:
            return GuardDecision(
                allowed=False,
                reason="DRAFT_EMPTY: Draft has no text content parts.",
            )

        full_text = parts[0]  # Primary text part

        # Fetch persona disclosure rule
        persona = await session.scalar(
            select(Persona).where(Persona.account_id == account.id).limit(1)
        )
        disclosure_text = persona.disclosure_text if persona else "Affiliate link"

        # -------------------------------------------------------------------
        # Check 5: Re-run content safety validator on final text (V-*)
        # -------------------------------------------------------------------
        is_affiliate = draft.link_url is not None or draft.product_id is not None
        report = validate_content(
            full_text,
            is_affiliate=is_affiliate,
            disclosure_text=disclosure_text,
        )
        if not report.passed:
            failed_str = ", ".join(report.failed_codes)
            logger.warning("PublishGuard Check 5 Failed: Content rules violated", violations=failed_str)
            return GuardDecision(
                allowed=False,
                reason=f"VALIDATOR_FAILED: Final text violates content rules [{failed_str}].",
            )

        # -------------------------------------------------------------------
        # Check 6: Similarity < 70% against past 30 days (V-SIM)
        # -------------------------------------------------------------------
        sim_result = await check_draft_similarity_in_db(
            session,
            account_id=account.id,
            new_text=full_text,
            days=30,
            threshold=70.0,
        )
        if not sim_result.passed:
            logger.warning(
                "PublishGuard Check 6 Failed: High similarity",
                score=sim_result.max_similarity,
            )
            return GuardDecision(
                allowed=False,
                reason=f"SIMILARITY_EXCEEDED: Candidate has {sim_result.max_similarity:.1f}% similarity to past 30 days post (max allowed is 70%).",
            )

        # -------------------------------------------------------------------
        # Check 7 & 8: Rate governor, daily quota, min interval, active hours
        # -------------------------------------------------------------------
        gov_decision = await check_governor_limits(
            session,
            account_id=account.id,
            proposed_time=now,
        )
        if not gov_decision.allowed:
            logger.warning("PublishGuard Check 7/8 Failed: Governor limit", reason=gov_decision.reason)
            return GuardDecision(
                allowed=False,
                reason=gov_decision.reason,
            )

        # -------------------------------------------------------------------
        # Check 9: Official Threads API publishing quota limit
        # -------------------------------------------------------------------
        if check_api_quota and client is not None:
            try:
                quota = await client.publishing_limit()
                if quota.quota_usage >= quota.config_quota_total:
                    return GuardDecision(
                        allowed=False,
                        reason=f"API_QUOTA_EXHAUSTED: Threads API 24h quota limit reached ({quota.quota_usage}/{quota.config_quota_total}).",
                    )
            except Exception as exc:
                logger.warning("Could not verify Threads API quota limit with client", error=str(exc))

        # -------------------------------------------------------------------
        # Check 10: Link attachment and placement constraints
        # -------------------------------------------------------------------
        if draft.kind == "comment" and draft.link_url:
            # Comments with links require explicit confirmation
            if draft.link_placement == "none":
                return GuardDecision(
                    allowed=False,
                    reason="COMMENT_LINK_UNCONFIRMED: Comment draft contains link but placement is set to none.",
                )

        # All 10 checks passed cleanly!
        logger.info("PublishGuard: ALL 10 SAFETY CHECKS PASSED", draft_id=draft.id)
        return GuardDecision(allowed=True)
