"""app/core/audit.py — Append-only audit trail logging.

All outward-impacting system actions (publish, reply, kill switch toggles, mode changes,
setting changes) MUST be recorded to the audit_log table.
No secrets (passwords, tokens, keys) are ever written to the audit log.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now_iso
from app.core.logging import get_logger
from app.db.models import AuditLog

logger = get_logger(__name__)

# Sensitive substrings to scrub from detail dicts
_SENSITIVE_KEYS = frozenset(["token", "password", "secret", "key", "authorization"])
_REDACTED = "[REDACTED]"


def _scrub_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively scrub sensitive keys from an audit detail dictionary."""
    scrubbed: dict[str, Any] = {}
    for k, v in data.items():
        if any(sub in k.lower() for sub in _SENSITIVE_KEYS):
            scrubbed[k] = _REDACTED
        elif isinstance(v, dict):
            scrubbed[k] = _scrub_dict(v)
        elif isinstance(v, list):
            scrubbed[k] = [
                _scrub_dict(item) if isinstance(item, dict) else item for item in v
            ]
        else:
            scrubbed[k] = v
    return scrubbed


async def record_audit(
    session: AsyncSession,
    *,
    actor: str,
    action: str,
    entity: str | None = None,
    entity_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditLog:
    """Record an append-only audit log entry to the database.

    Args:
        session: Active async database session.
        actor: Who initiated the action ('admin', 'system', 'telegram').
        action: Semantic action name ('publish', 'kill_switch_on', 'mode_change', etc.).
        entity: Entity type affected ('system_state', 'draft', 'account', etc.).
        entity_id: Identifier of the affected entity.
        detail: Optional structured details dictionary (automatically scrubbed of secrets).

    Returns:
        The newly created AuditLog record.
    """
    detail_json: str | None = None
    if detail is not None:
        clean_detail = _scrub_dict(detail)
        detail_json = json.dumps(clean_detail, separators=(",", ":"))

    entry = AuditLog(
        at=utc_now_iso(),
        actor=actor,
        action=action,
        entity=entity,
        entity_id=entity_id,
        detail=detail_json,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)

    logger.info(
        "Audit log recorded",
        actor=actor,
        action=action,
        entity=entity,
        entity_id=entity_id,
    )
    return entry


# Semantic alias matching codebase convention
record_audit_log = record_audit



async def get_recent_audit_logs(
    session: AsyncSession,
    *,
    limit: int = 100,
    offset: int = 0,
    action: str | None = None,
    actor: str | None = None,
) -> list[AuditLog]:
    """Retrieve recent audit log entries ordered newest first."""
    stmt = select(AuditLog).order_by(AuditLog.at.desc()).limit(limit).offset(offset)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor:
        stmt = stmt.where(AuditLog.actor == actor)

    result = await session.scalars(stmt)
    return list(result.all())

