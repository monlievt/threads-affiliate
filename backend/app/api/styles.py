"""app/api/styles.py — CRUD endpoints for Content Styles.

Follows strict safety principles:
- Soft delete: DELETE endpoints perform soft-delete by setting status = 'archived'.
- All mutations require admin session + CSRF token, and append an audit log entry.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_log
from app.core.security import get_current_admin, require_csrf
from app.db.models import Style, utc_now_iso
from app.db.session import get_db
from app.schemas.catalog import StyleCreate, StyleResponse, StyleUpdate

router = APIRouter(prefix="/api/styles", tags=["styles"])


@router.get("", response_model=list[StyleResponse])
async def list_styles(
    include_archived: bool = Query(default=False, description="Include archived styles"),
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> list[StyleResponse]:
    """List styles, optionally filtering out archived profiles."""
    query = select(Style)
    if not include_archived:
        query = query.where(Style.status != "archived")
    query = query.order_by(Style.name.asc())

    result = await session.execute(query)
    styles = result.scalars().all()
    return [StyleResponse.from_orm_model(s) for s in styles]


@router.get("/{style_id}", response_model=StyleResponse)
async def get_style(
    style_id: str,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> StyleResponse:
    """Get single style by ID."""
    result = await session.execute(select(Style).where(Style.id == style_id))
    style = result.scalar_one_or_none()
    if not style:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Style with ID {style_id!r} not found.",
        )
    return StyleResponse.from_orm_model(style)


@router.post("", response_model=StyleResponse, status_code=status.HTTP_201_CREATED)
async def create_style(
    payload: StyleCreate,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> StyleResponse:
    """Create a new style profile."""
    existing = await session.execute(select(Style).where(Style.name == payload.name))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Style with name {payload.name!r} already exists.",
        )

    good_json = json.dumps(payload.good_examples) if payload.good_examples else None
    bad_json = json.dumps(payload.bad_examples) if payload.bad_examples else None

    style = Style(
        name=payload.name,
        description=payload.description,
        tone_rules=payload.tone_rules,
        max_chars=payload.max_chars,
        good_examples=good_json,
        bad_examples=bad_json,
        status="active",
    )
    session.add(style)
    await session.commit()
    await session.refresh(style)

    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="create",
        entity="styles",
        entity_id=style.id,
        detail={"name": style.name},
    )

    return StyleResponse.from_orm_model(style)


@router.put("/{style_id}", response_model=StyleResponse)
async def update_style(
    style_id: str,
    payload: StyleUpdate,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> StyleResponse:
    """Update style profile attributes."""
    result = await session.execute(select(Style).where(Style.id == style_id))
    style = result.scalar_one_or_none()
    if not style:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Style with ID {style_id!r} not found.",
        )

    if payload.name is not None and payload.name != style.name:
        existing = await session.execute(
            select(Style).where(Style.name == payload.name, Style.id != style_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Style with name {payload.name!r} already exists.",
            )
        style.name = payload.name

    if payload.description is not None:
        style.description = payload.description
    if payload.tone_rules is not None:
        style.tone_rules = payload.tone_rules
    if payload.max_chars is not None:
        style.max_chars = payload.max_chars
    if payload.good_examples is not None:
        style.good_examples = json.dumps(payload.good_examples)
    if payload.bad_examples is not None:
        style.bad_examples = json.dumps(payload.bad_examples)
    if payload.status is not None:
        style.status = payload.status

    style.updated_at = utc_now_iso()
    await session.commit()
    await session.refresh(style)

    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="update",
        entity="styles",
        entity_id=style.id,
        detail={"updated_fields": payload.model_dump(exclude_unset=True)},
    )

    return StyleResponse.from_orm_model(style)


@router.delete("/{style_id}", response_model=StyleResponse)
async def delete_style(
    style_id: str,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> StyleResponse:
    """Soft-delete a style profile (sets status = 'archived'). Hard delete is prohibited."""
    result = await session.execute(select(Style).where(Style.id == style_id))
    style = result.scalar_one_or_none()
    if not style:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Style with ID {style_id!r} not found.",
        )

    style.status = "archived"
    style.updated_at = utc_now_iso()
    await session.commit()
    await session.refresh(style)

    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="archive",
        entity="styles",
        entity_id=style.id,
        detail={"name": style.name, "status": "archived"},
    )

    return StyleResponse.from_orm_model(style)
