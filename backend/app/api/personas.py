"""app/api/personas.py — CRUD endpoints for Account Personas.

Follows strict safety principles:
- Validates disclosure rules (V-DISC: non-empty disclosure text, valid position).
- All mutations require admin session + CSRF token, and append an audit log entry.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_log
from app.core.security import get_current_admin, require_csrf
from app.db.models import Account, Persona, utc_now_iso
from app.db.session import get_db
from app.schemas.catalog import PersonaCreate, PersonaResponse, PersonaUpdate

router = APIRouter(prefix="/api/personas", tags=["personas"])


@router.get("", response_model=list[PersonaResponse])
async def list_personas(
    account_id: str | None = Query(default=None, description="Filter by account ID"),
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> list[PersonaResponse]:
    """List personas with optional account filter."""
    query = select(Persona)
    if account_id:
        query = query.where(Persona.account_id == account_id)
    query = query.order_by(Persona.name.asc())

    result = await session.execute(query)
    personas = result.scalars().all()
    return [PersonaResponse.from_orm_model(p) for p in personas]


@router.get("/{persona_id}", response_model=PersonaResponse)
async def get_persona(
    persona_id: str,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> PersonaResponse:
    """Get single persona by ID."""
    result = await session.execute(select(Persona).where(Persona.id == persona_id))
    persona = result.scalar_one_or_none()
    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona with ID {persona_id!r} not found.",
        )
    return PersonaResponse.from_orm_model(persona)


@router.post("", response_model=PersonaResponse, status_code=status.HTTP_201_CREATED)
async def create_persona(
    payload: PersonaCreate,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> PersonaResponse:
    """Create a new account persona with affiliate disclosure configuration."""
    # Verify account exists
    acc = await session.execute(select(Account).where(Account.id == payload.account_id))
    if not acc.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account with ID {payload.account_id!r} not found.",
        )

    persona = Persona(
        account_id=payload.account_id,
        name=payload.name,
        voice=payload.voice,
        avoid=payload.avoid,
        disclosure_text=payload.disclosure_text,
        disclosure_position=payload.disclosure_position,
    )
    session.add(persona)
    await session.commit()
    await session.refresh(persona)

    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="create",
        entity="personas",
        entity_id=persona.id,
        detail={"name": persona.name, "account_id": persona.account_id},
    )

    return PersonaResponse.from_orm_model(persona)


@router.put("/{persona_id}", response_model=PersonaResponse)
async def update_persona(
    persona_id: str,
    payload: PersonaUpdate,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> PersonaResponse:
    """Update persona voice or disclosure attributes."""
    result = await session.execute(select(Persona).where(Persona.id == persona_id))
    persona = result.scalar_one_or_none()
    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona with ID {persona_id!r} not found.",
        )

    if payload.name is not None:
        persona.name = payload.name
    if payload.voice is not None:
        persona.voice = payload.voice
    if payload.avoid is not None:
        persona.avoid = payload.avoid
    if payload.disclosure_text is not None:
        persona.disclosure_text = payload.disclosure_text
    if payload.disclosure_position is not None:
        persona.disclosure_position = payload.disclosure_position

    persona.updated_at = utc_now_iso()
    await session.commit()
    await session.refresh(persona)

    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="update",
        entity="personas",
        entity_id=persona.id,
        detail={"updated_fields": payload.model_dump(exclude_unset=True)},
    )

    return PersonaResponse.from_orm_model(persona)


@router.delete("/{persona_id}", status_code=status.HTTP_200_OK)
async def delete_persona(
    persona_id: str,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> dict[str, Any]:
    """Delete a persona profile."""
    result = await session.execute(select(Persona).where(Persona.id == persona_id))
    persona = result.scalar_one_or_none()
    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona with ID {persona_id!r} not found.",
        )

    persona_name = persona.name
    await session.delete(persona)
    await session.commit()

    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="delete",
        entity="personas",
        entity_id=persona_id,
        detail={"name": persona_name},
    )

    return {"status": "ok", "deleted_id": persona_id}
