"""app/api/comments.py — Value-First Comments (Feature 10) endpoints.

Follows strict safety principles:
1. Always manual review: Comments are never automatically published without explicit operator action.
2. Rate limits: Clamped by WarmupTier.max_replies_per_day and HARD_MAX_REPLIES_PER_DAY.
3. Prominent link warnings: Value-first priority.
4. Avoid list enforcement: Filters aggressive self-promotion, prices, and spam.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, time, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.content.llm.base import LLMResponse
from app.content.llm.fake import FakeLLMProvider
from app.content.llm.gemini import GeminiLLMProvider
from app.content.prompts.f10_comment import AVOID_LIST_COMMON, build_comment_prompt
from app.core.audit import record_audit_log
from app.core.clock import utc_now, utc_now_iso
from app.core.security import get_current_admin, require_csrf
from app.db.models import Account, AuditLog, Niche, Persona, Post, Product
from app.db.session import get_db
from app.safety.warmup import get_warmup_tier
from app.schemas.comments import (
    CommentGenerateRequest,
    CommentGenerateResponse,
    CommentOption,
    CommentPublishRequest,
    CommentPublishResponse,
    CommentsQuotaResponse,
)

router = APIRouter(prefix="/api/comments", tags=["comments"])

PRICE_REGEX = re.compile(
    r"([$€£¥]|\b\d+(\.\d{1,2})?\s*(usd|dollars|bucks|cents)\b|\b\d+%\s*off\b|\b(sale|discount|price|cheap|promo)\b)",
    re.IGNORECASE,
)


async def _get_primary_account(session: AsyncSession) -> Account:
    res = await session.execute(select(Account).where(Account.status == "active").limit(1))
    acc = res.scalar_one_or_none()
    if acc:
        return acc

    # Default fallback account
    now = utc_now_iso()
    acc = Account(
        id="acc_default",
        username="affiliate_curator",
        country_code="US",
        timezone="America/New_York",
        active_hours_start=9,
        active_hours_end=21,
        automation_mode="manual_approve",
        warmup_started_at=now,
        status="active",
        created_at=now,
        updated_at=now,
    )
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    return acc


async def _get_daily_replies_count(session: AsyncSession, account_id: str) -> int:
    """Count replies performed today (both via clipboard copy and API publish)."""
    now = utc_now()
    start_of_day_utc = datetime.combine(now.date(), time.min, tzinfo=timezone.utc).isoformat()

    # Query audit logs for actions performed today
    res = await session.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.action.in_(["copy_comment_clipboard", "publish_comment_api"]),
            AuditLog.at >= start_of_day_utc,
        )
    )
    count = res.scalar_one() or 0
    return count


def _extract_target_post_id(url: str) -> str | None:
    """Extract Threads post ID or shortcode from URL."""
    # Pattern: https://www.threads.net/@user/post/C4xyz123 or similar
    match = re.search(r"/post/([A-Za-z0-9_-]+)", url)
    return match.group(1) if match else None


def _get_llm_provider():
    if settings.GEMINI_API_KEY:
        try:
            return GeminiLLMProvider(api_key=settings.GEMINI_API_KEY, model_name=settings.GEMINI_MODEL)
        except Exception:
            return FakeLLMProvider()
    return FakeLLMProvider()


@router.get("/quota", response_model=CommentsQuotaResponse)
async def get_comments_quota(
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> CommentsQuotaResponse:
    """Retrieve daily comment limit, current usage, and safety avoid list."""
    account = await _get_primary_account(session)
    warmup = get_warmup_tier(account.warmup_started_at)
    daily_limit = min(warmup.max_replies_per_day, settings.HARD_MAX_REPLIES_PER_DAY)

    replies_today = await _get_daily_replies_count(session, account.id)
    remaining = max(0, daily_limit - replies_today)

    return CommentsQuotaResponse(
        replies_today=replies_today,
        max_replies_today=daily_limit,
        hard_max_replies=settings.HARD_MAX_REPLIES_PER_DAY,
        remaining_today=remaining,
        is_quota_full=remaining <= 0,
        avoid_list=AVOID_LIST_COMMON,
    )


@router.post("/generate", response_model=CommentGenerateResponse)
async def generate_comments(
    payload: CommentGenerateRequest,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> CommentGenerateResponse:
    """Generate 2-3 value-first comment options using LLM with safety checking."""
    account = await _get_primary_account(session)
    warmup = get_warmup_tier(account.warmup_started_at)
    daily_limit = min(warmup.max_replies_per_day, settings.HARD_MAX_REPLIES_PER_DAY)

    replies_today = await _get_daily_replies_count(session, account.id)
    if replies_today >= daily_limit:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Batas kuota harian komentar ({daily_limit} komentar/hari) telah tercapai. Istirahatkan akun untuk menjaga reputasi Threads.",
        )

    # Validate target URL format
    if "threads.net" not in payload.target_post_url.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL target harus merupakan tautan postingan Threads resmi (threads.net).",
        )

    target_id = _extract_target_post_id(payload.target_post_url)

    # Optional Niche & Persona lookup
    niche_name = None
    if payload.niche_id:
        niche = await session.get(Niche, payload.niche_id)
        if niche:
            niche_name = niche.name

    persona_voice = None
    if payload.persona_id:
        persona = await session.get(Persona, payload.persona_id)
        if persona:
            persona_voice = persona.voice_description

    # Product link lookup if include_link is True
    link_url = None
    if payload.include_link and payload.product_id:
        prod = await session.get(Product, payload.product_id)
        if prod:
            link_url = prod.benable_url

    # Build prompt
    sys_prompt, user_prompt = build_comment_prompt(
        target_post_text=payload.target_post_text,
        target_post_url=payload.target_post_url,
        niche_name=niche_name,
        persona_voice=persona_voice,
        include_link=payload.include_link,
        link_url=link_url,
        strategy=payload.strategy,
    )

    llm = _get_llm_provider()
    try:
        llm_resp: LLMResponse = await llm.generate_text(
            prompt=user_prompt,
            system_instruction=sys_prompt,
            max_tokens=600,
            temperature=0.7,
        )
        content_text = llm_resp.content.strip()
    except Exception:
        content_text = ""

    # Parse JSON options
    parsed_options: list[dict[str, str]] = []
    if content_text:
        try:
            # Clean markdown codeblocks if any
            clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", content_text, flags=re.MULTILINE).strip()
            data = json.loads(clean_json)
            if isinstance(data, dict) and "options" in data:
                parsed_options = data["options"]
        except Exception:
            pass

    # Fallback options if LLM did not return strict JSON
    if not parsed_options:
        parsed_options = [
            {
                "strategy": "insight",
                "text": "Great perspective on this. One subtle thing that helped me with similar workflows is keeping cable routing minimal before adding accessories.",
            },
            {
                "strategy": "relate",
                "text": "Felt this so much. Took me way longer than it should have to realize keeping it minimal saves hours of cleaning.",
            },
            {
                "strategy": "question",
                "text": "Curious how you're dealing with cable routing behind the riser — did you use adhesive clips or an under-desk raceway?",
            },
        ]

    # Validate each option
    strategy_labels = {
        "insight": "💡 Insight Bernilai",
        "relate": "🤝 Empati & Relate",
        "question": "❓ Pemantik Diskusi",
        "curator_tip": "✨ Tips Kurasi",
    }

    validated_options: list[CommentOption] = []
    for idx, opt in enumerate(parsed_options, start=1):
        strat = opt.get("strategy", "insight")
        if strat not in strategy_labels:
            strat = "insight"
        raw_text = opt.get("text", "").strip()

        # Append link if requested and not present
        if payload.include_link and link_url and link_url not in raw_text:
            raw_text = f"{raw_text} ({link_url})"

        has_link = bool(re.search(r"https?://", raw_text))

        issues: list[str] = []
        # Check price violation
        if PRICE_REGEX.search(raw_text):
            issues.append("V-PRICE: Terdeteksi angka harga atau diskon.")

        # Check character length (max 300)
        if len(raw_text) > 300:
            issues.append("V-LEN: Panjang teks melebihi 300 karakter.")

        # Check generic avoid keywords
        for avoid in ["great post!", "nice!", "check my bio", "dm me"]:
            if avoid in raw_text.lower():
                issues.append(f"V-SPAM: Mengandung frasa terlarang '{avoid}'.")

        validated_options.append(
            CommentOption(
                option_id=f"opt_{idx}",
                strategy=strat,  # type: ignore[arg-type]
                strategy_label=strategy_labels[strat],
                text=raw_text,
                char_count=len(raw_text),
                has_link=has_link,
                link_url=link_url if has_link else None,
                safety_valid=len(issues) == 0,
                safety_issues=issues,
            )
        )

    remaining = max(0, daily_limit - replies_today)

    return CommentGenerateResponse(
        target_post_url=payload.target_post_url,
        target_post_id=target_id,
        options=validated_options,
        daily_replies_used=replies_today,
        daily_replies_limit=daily_limit,
        hard_max_replies=settings.HARD_MAX_REPLIES_PER_DAY,
        remaining_replies_today=remaining,
        avoid_list=AVOID_LIST_COMMON,
    )


@router.post("/publish", response_model=CommentPublishResponse)
async def publish_or_copy_comment(
    payload: CommentPublishRequest,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> CommentPublishResponse:
    """Record manual comment action (copied to clipboard or published via API)."""
    account = await _get_primary_account(session)
    warmup = get_warmup_tier(account.warmup_started_at)
    daily_limit = min(warmup.max_replies_per_day, settings.HARD_MAX_REPLIES_PER_DAY)

    replies_today = await _get_daily_replies_count(session, account.id)

    # Log audit event
    action_name = "publish_comment_api" if payload.action_type == "publish_api" else "copy_comment_clipboard"

    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action=action_name,
        entity="comments",
        detail={
            "target_url": payload.target_post_url,
            "char_count": len(payload.selected_text),
            "has_link": bool(payload.link_url),
            "action_type": payload.action_type,
        },
    )

    new_used = replies_today + 1
    remaining = max(0, daily_limit - new_used)

    return CommentPublishResponse(
        success=True,
        message="Komentar berhasil diproses dan dicatat ke kuota harian."
        if payload.action_type == "publish_api"
        else "Teks komentar disalin ke clipboard dan dicatat ke kuota harian.",
        action_type=payload.action_type,
        threads_reply_id=None,
        daily_replies_used=new_used,
        remaining_replies_today=remaining,
    )
