"""app/api/drafts.py — Draft review queue, inline editor, and live validation endpoints.

Strict Safety & Compliance:
1. All mutations require admin session + CSRF protection.
2. Edit operations re-run comprehensive content validators (V-LEN s/d V-MISC) before persisting.
3. Every approval, rejection, and edit appends an entry to audit_trail.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import record_audit_log
from app.core.clock import utc_now_iso
from app.core.security import get_current_admin, require_csrf
from app.db.models import Draft, Style
from app.db.session import get_db
from app.safety.validators import validate_content
from app.schemas.drafts import (
    BatchApproveResponse,
    DraftEditRequest,
    DraftRejectRequest,
    DraftResponse,
    RuleValidationItem,
    ValidateTextRequest,
    ValidateTextResponse,
)

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


def compute_text_hash(text: str) -> str:
    """Normalize and compute SHA-256 hash."""
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@router.get("", response_model=list[DraftResponse])
async def list_drafts(
    status_filter: str | None = Query(default=None, alias="status", description="Filter by draft status"),
    niche_id: str | None = Query(default=None, description="Filter by niche ID"),
    style_id: str | None = Query(default=None, description="Filter by style ID"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> list[DraftResponse]:
    """List drafts with optional status, niche, style filters and pagination."""
    query = (
        select(Draft)
        .options(
            selectinload(Draft.niche),
            selectinload(Draft.style),
            selectinload(Draft.product),
        )
    )

    if status_filter:
        query = query.where(Draft.status == status_filter)
    if niche_id:
        query = query.where(Draft.niche_id == niche_id)
    if style_id:
        query = query.where(Draft.style_id == style_id)

    query = query.order_by(Draft.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(query)
    drafts = result.scalars().all()
    return [DraftResponse.from_orm_model(d) for d in drafts]


@router.get("/{draft_id}", response_model=DraftResponse)
async def get_draft(
    draft_id: str,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> DraftResponse:
    """Get single draft by ID with full details."""
    query = (
        select(Draft)
        .options(
            selectinload(Draft.niche),
            selectinload(Draft.style),
            selectinload(Draft.product),
        )
        .where(Draft.id == draft_id)
    )
    result = await session.execute(query)
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft with ID {draft_id!r} not found.",
        )
    return DraftResponse.from_orm_model(draft)


@router.post("/{draft_id}/approve", response_model=DraftResponse)
async def approve_draft(
    draft_id: str,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> DraftResponse:
    """Approve a pending draft for publication scheduling."""
    query = (
        select(Draft)
        .options(
            selectinload(Draft.niche),
            selectinload(Draft.style),
            selectinload(Draft.product),
        )
        .where(Draft.id == draft_id)
    )
    result = await session.execute(query)
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft with ID {draft_id!r} not found.",
        )

    if draft.status in ("approved", "scheduled", "publishing", "published"):
        return DraftResponse.from_orm_model(draft)

    if draft.status not in ("pending_review", "generated"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve draft with status {draft.status!r}.",
        )

    now = utc_now_iso()
    draft.status = "approved"
    draft.reviewed_at = now
    draft.updated_at = now
    await session.commit()
    await session.refresh(draft)

    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="approve_draft",
        entity="drafts",
        entity_id=draft.id,
        detail={"new_status": "approved"},
    )

    return DraftResponse.from_orm_model(draft)


@router.post("/{draft_id}/reject", response_model=DraftResponse)
async def reject_draft(
    draft_id: str,
    payload: DraftRejectRequest,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> DraftResponse:
    """Reject a draft with optional feedback reason."""
    query = (
        select(Draft)
        .options(
            selectinload(Draft.niche),
            selectinload(Draft.style),
            selectinload(Draft.product),
        )
        .where(Draft.id == draft_id)
    )
    result = await session.execute(query)
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft with ID {draft_id!r} not found.",
        )

    now = utc_now_iso()
    draft.status = "rejected"
    draft.reject_reason = payload.reason or "Rejected by operator"
    draft.reviewed_at = now
    draft.updated_at = now
    await session.commit()
    await session.refresh(draft)

    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="reject_draft",
        entity="drafts",
        entity_id=draft.id,
        detail={"reason": draft.reject_reason},
    )

    return DraftResponse.from_orm_model(draft)


@router.put("/{draft_id}", response_model=DraftResponse)
async def edit_draft(
    draft_id: str,
    payload: DraftEditRequest,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> DraftResponse:
    """Edit draft text inline with mandatory content safety validation."""
    query = (
        select(Draft)
        .options(
            selectinload(Draft.niche),
            selectinload(Draft.style),
            selectinload(Draft.product),
        )
        .where(Draft.id == draft_id)
    )
    result = await session.execute(query)
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft with ID {draft_id!r} not found.",
        )

    if draft.status in ("publishing", "published"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot edit draft in '{draft.status}' state.",
        )

    max_chars = draft.style.max_chars if draft.style else 500
    is_affiliate = draft.product_id is not None
    clean_text = payload.text.strip()

    # Mandatory real-time content safety validation
    val_report = validate_content(
        clean_text,
        is_affiliate=is_affiliate,
        max_chars=max_chars,
    )

    if not val_report.valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Edited text violates content safety rules.",
                "failed_codes": val_report.failed_codes,
                "report": val_report.to_dict(),
            },
        )

    now = utc_now_iso()
    # Update parts
    new_parts = [{"part_index": 1, "text": clean_text, "char_count": len(clean_text)}]
    draft.parts = json.dumps(new_parts)
    draft.text_hash = compute_text_hash(clean_text)
    draft.validator_report = json.dumps(val_report.to_dict())
    if payload.scheduled_at is not None:
        draft.scheduled_at = payload.scheduled_at

    draft.updated_at = now
    await session.commit()
    await session.refresh(draft)

    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="edit_draft",
        entity="drafts",
        entity_id=draft.id,
        detail={"char_count": len(clean_text), "scheduled_at": draft.scheduled_at},
    )

    return DraftResponse.from_orm_model(draft)


@router.post("/batch-approve", response_model=BatchApproveResponse)
async def batch_approve_eligible_drafts(
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> BatchApproveResponse:
    """Batch approve all unreviewed drafts that have passed all validator rules."""
    query = (
        select(Draft)
        .where(Draft.status == "pending_review")
        .order_by(Draft.created_at.asc())
    )
    result = await session.execute(query)
    drafts = result.scalars().all()

    approved_ids: list[str] = []
    now = utc_now_iso()

    for d in drafts:
        is_clean = True
        if d.validator_report:
            try:
                rep = json.loads(d.validator_report)
                if not rep.get("valid", False):
                    is_clean = False
            except Exception:
                is_clean = False

        if is_clean:
            d.status = "approved"
            d.reviewed_at = now
            d.updated_at = now
            approved_ids.append(d.id)

    if approved_ids:
        await session.commit()
        await record_audit_log(
            session,
            actor=admin.get("sub", "admin"),
            action="batch_approve_drafts",
            entity="drafts",
            detail={"approved_count": len(approved_ids), "ids": approved_ids},
        )

    return BatchApproveResponse(
        total_eligible=len(drafts),
        approved_count=len(approved_ids),
        approved_ids=approved_ids,
    )


@router.post("/validate-text", response_model=ValidateTextResponse)
async def validate_text_realtime(
    payload: ValidateTextRequest,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> ValidateTextResponse:
    """Real-time validation for inline draft editor while user is typing."""
    max_chars = 500
    if payload.style_id:
        style = await session.scalar(select(Style).where(Style.id == payload.style_id))
        if style:
            max_chars = style.max_chars

    report = validate_content(
        payload.text,
        is_affiliate=payload.is_affiliate,
        disclosure_text=payload.disclosure_text,
        max_chars=max_chars,
    )

    results_dict: dict[str, RuleValidationItem] = {}
    for code, item in report.results.items():
        results_dict[code] = RuleValidationItem(
            code=code,
            valid=item.valid,
            reason=item.reason,
        )

    return ValidateTextResponse(
        valid=report.valid,
        char_count=len(payload.text),
        max_chars=max_chars,
        failed_codes=report.failed_codes,
        results=results_dict,
    )
