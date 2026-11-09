"""app/api/niches.py — CRUD endpoints for Niches.

Follows strict safety principles:
- No hard delete: DELETE endpoints perform soft-delete by setting status = 'archived'.
- All mutations (POST, PUT, DELETE) require admin session + CSRF token.
- All mutations append an audit log entry.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_log
from app.core.security import get_current_admin, require_csrf
from app.db.models import Niche, utc_now_iso
from app.db.session import get_db
from app.schemas.catalog import NicheCreate, NicheResponse, NicheUpdate

router = APIRouter(prefix="/api/niches", tags=["niches"])


@router.get("", response_model=list[NicheResponse])
async def list_niches(
    include_archived: bool = Query(default=False, description="Include archived niches"),
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> list[NicheResponse]:
    """List all niches, optionally filtering out archived niches."""
    query = select(Niche)
    if not include_archived:
        query = query.where(Niche.status != "archived")
    query = query.order_by(Niche.name.asc())

    result = await session.execute(query)
    niches = result.scalars().all()
    return [NicheResponse.from_orm_model(n) for n in niches]


@router.get("/{niche_id}", response_model=NicheResponse)
async def get_niche(
    niche_id: str,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> NicheResponse:
    """Get single niche by ID."""
    result = await session.execute(select(Niche).where(Niche.id == niche_id))
    niche = result.scalar_one_or_none()
    if not niche:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Niche with ID {niche_id!r} not found.",
        )
    return NicheResponse.from_orm_model(niche)


@router.post("", response_model=NicheResponse, status_code=status.HTTP_201_CREATED)
async def create_niche(
    payload: NicheCreate,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> NicheResponse:
    """Create a new niche."""
    # Check for name uniqueness
    existing = await session.execute(select(Niche).where(Niche.name == payload.name))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Niche with name {payload.name!r} already exists.",
        )

    keywords_json = json.dumps(payload.keywords) if payload.keywords else None
    niche = Niche(
        name=payload.name,
        description=payload.description,
        keywords=keywords_json,
        status="active",
    )
    session.add(niche)
    await session.commit()
    await session.refresh(niche)

    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="create",
        entity="niches",
        entity_id=niche.id,
        detail={"name": niche.name},
    )

    return NicheResponse.from_orm_model(niche)


@router.put("/{niche_id}", response_model=NicheResponse)
async def update_niche(
    niche_id: str,
    payload: NicheUpdate,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> NicheResponse:
    """Update existing niche attributes."""
    result = await session.execute(select(Niche).where(Niche.id == niche_id))
    niche = result.scalar_one_or_none()
    if not niche:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Niche with ID {niche_id!r} not found.",
        )

    if payload.name is not None and payload.name != niche.name:
        existing = await session.execute(
            select(Niche).where(Niche.name == payload.name, Niche.id != niche_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Niche with name {payload.name!r} already exists.",
            )
        niche.name = payload.name

    if payload.description is not None:
        niche.description = payload.description
    if payload.keywords is not None:
        niche.keywords = json.dumps(payload.keywords)
    if payload.status is not None:
        niche.status = payload.status

    niche.updated_at = utc_now_iso()
    await session.commit()
    await session.refresh(niche)

    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="update",
        entity="niches",
        entity_id=niche.id,
        detail={"updated_fields": payload.model_dump(exclude_unset=True)},
    )

    return NicheResponse.from_orm_model(niche)


@router.delete("/{niche_id}", response_model=NicheResponse)
async def delete_niche(
    niche_id: str,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> NicheResponse:
    """Soft-delete a niche (sets status = 'archived'). Hard delete is prohibited."""
    result = await session.execute(select(Niche).where(Niche.id == niche_id))
    niche = result.scalar_one_or_none()
    if not niche:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Niche with ID {niche_id!r} not found.",
        )

    niche.status = "archived"
    niche.updated_at = utc_now_iso()
    await session.commit()
    await session.refresh(niche)

    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="archive",
        entity="niches",
        entity_id=niche.id,
        detail={"name": niche.name, "status": "archived"},
    )

    return NicheResponse.from_orm_model(niche)
