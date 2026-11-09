"""app/content/engine.py — Content generation engine coordinating LLM, prompts, validation, and draft creation."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.clock import utc_now, utc_now_iso
from app.core.logging import get_logger
from app.content.llm.base import LLMProvider
from app.content.llm.gemini import GeminiLLMProvider
from app.content.llm.usage import check_and_increment_llm_budget
from app.content.parser import GenerationOutput, parse_generation_output
from app.content.prompts.p_v1 import PROMPT_VERSION, build_p_v1_prompt
from app.db.models import Account, Draft, Niche, Persona, Product, Style
from app.safety.automation_policy import (
    determine_draft_initial_status,
    evaluate_auto_downgrade,
)
from app.safety.similarity import (
    check_draft_similarity_in_db,
    compute_normalized_hash,
)
from app.safety.validators import validate_content

logger = get_logger(__name__)


async def get_recent_openers(
    session: AsyncSession,
    account_id: str,
    limit: int = 10,
) -> list[str]:
    """Fetch the opening sentence or words from the last N created drafts."""
    stmt = (
        select(Draft.parts)
        .where(Draft.account_id == account_id)
        .order_by(Draft.created_at.desc())
        .limit(limit)
    )
    rows = (await session.scalars(stmt)).all()
    openers: list[str] = []

    for parts_json in rows:
        try:
            parts = json.loads(parts_json)
            text = parts[0] if isinstance(parts, list) and parts else str(parts)
            first_sentence = text.strip().split(".")[0].strip()
            if first_sentence:
                openers.append(first_sentence)
        except Exception:
            continue

    return openers


class ContentEngine:
    """Coordinates prompt rendering, LLM completion, validation, and draft persistence."""

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        model_name: str | None = None,
    ) -> None:
        self.model_name = model_name or settings.GEMINI_MODEL_TEXT
        self.llm = llm_provider or GeminiLLMProvider(model=self.model_name)

    async def generate_drafts(
        self,
        session: AsyncSession,
        *,
        account_id: str,
        niche_id: str,
        style_id: str,
        product_id: str | None = None,
        arm_id: str | None = None,
        num_variants: int = 3,
    ) -> list[Draft]:
        """Generate post variants, run validation, and store them into the drafts table.

        - Variants passing all checks are saved with status='pending_review'.
        - Variants failing any rule are saved with status='rejected_auto' + reject_reason.
        - llm_raw_response is recorded for auditing and inspection.
        """
        # 1. Resolve required DB entities
        account = await session.scalar(select(Account).where(Account.id == account_id))
        if not account:
            raise ValueError(f"Account {account_id!r} not found.")

        niche = await session.scalar(select(Niche).where(Niche.id == niche_id))
        if not niche:
            raise ValueError(f"Niche {niche_id!r} not found.")

        style = await session.scalar(select(Style).where(Style.id == style_id))
        if not style:
            raise ValueError(f"Style {style_id!r} not found.")

        product: Product | None = None
        if product_id:
            product = await session.scalar(select(Product).where(Product.id == product_id))
            if not product:
                raise ValueError(f"Product {product_id!r} not found.")

        persona = await session.scalar(
            select(Persona).where(Persona.account_id == account_id).limit(1)
        )
        if not persona:
            # Fallback persona if none exists yet
            persona = Persona(
                account_id=account.id,
                name="Default Curator",
                voice="Curator finding useful products",
                avoid="Hype, hard sell, spam",
                disclosure_text="Affiliate link",
                disclosure_position="end",
            )

        # 2. Check and increment daily LLM call budget
        await check_and_increment_llm_budget(session, model=self.model_name)

        # 3. Retrieve recent openers
        recent_openers = await get_recent_openers(session, account_id=account.id, limit=10)

        # 4. Construct p_v1 prompt
        system_prompt, user_prompt = build_p_v1_prompt(
            persona=persona,
            style=style,
            niche=niche,
            product=product,
            country=account.country_code or "US",
            recent_openers=recent_openers,
            num_variants=num_variants,
        )

        # 5. Call LLM provider
        raw_output = await self.llm.generate(
            user_prompt,
            system=system_prompt,
            temperature=0.85,
        )

        # 6. Parse structured variants
        parsed_output: GenerationOutput = parse_generation_output(raw_output)

        # 7. Evaluate each variant and persist
        created_drafts: list[Draft] = []
        now = utc_now()
        now_iso = now.isoformat()
        expires_at_iso = (now + timedelta(hours=48)).isoformat()

        # Check if account requires auto-downgrade due to recent incidents (docs/06 §6)
        await evaluate_auto_downgrade(session, account)

        is_affiliate = product is not None

        for variant in parsed_output.variants:
            text = variant.parts[0] if variant.parts else ""
            text_hash = compute_normalized_hash(text)

            # A. Content safety validator (V-*)
            val_report = validate_content(
                text,
                is_affiliate=is_affiliate,
                disclosure_text=persona.disclosure_text,
                max_chars=style.max_chars,
                recent_openers=recent_openers,
            )

            # B. Similarity check (V-SIM)
            sim_report = await check_draft_similarity_in_db(
                session,
                account_id=account.id,
                new_text=text,
                days=30,
                threshold=70.0,
            )

            # Determine draft status based on validation and automation mode
            reviewed_at_iso = None
            if not val_report.passed:
                status = "rejected_auto"
                reason = f"Violated content rules: {', '.join(val_report.failed_codes)}"
            elif not sim_report.passed:
                status = "rejected_auto"
                reason = f"Similarity too high: {sim_report.max_similarity:.1f}% >= 70%"
            else:
                status, approval_note = determine_draft_initial_status(account, val_passed=True)
                reason = approval_note
                if status == "approved":
                    reviewed_at_iso = now_iso

            draft = Draft(
                account_id=account.id,
                kind="post" if len(variant.parts) <= 1 else "thread",
                arm_id=arm_id,
                niche_id=niche.id,
                style_id=style.id,
                product_id=product.id if product else None,
                prompt_version=PROMPT_VERSION,
                llm_model=self.model_name,
                parts=json.dumps(variant.parts),
                llm_raw_response=raw_output,
                link_url=product.benable_url if product and variant.has_link else None,
                link_placement=variant.link_placement if variant.has_link else "none",
                status=status,
                reject_reason=reason if status != "approved" else None,
                reviewed_at=reviewed_at_iso,
                validator_report=json.dumps(val_report.to_dict()),
                text_hash=text_hash,
                expires_at=expires_at_iso,
                created_at=now_iso,
                updated_at=now_iso,
            )

            session.add(draft)
            created_drafts.append(draft)

        await session.commit()
        for d in created_drafts:
            await session.refresh(d)

        logger.info(
            "Draft generation batch completed",
            total_generated=len(created_drafts),
            pending_review=sum(1 for d in created_drafts if d.status == "pending_review"),
            rejected_auto=sum(1 for d in created_drafts if d.status == "rejected_auto"),
        )

        return created_drafts
