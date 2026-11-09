"""app/safety/killswitch.py — Global emergency kill switch manager.

Hard Rules (from docs/06 & AGENTS.md):
- Default ON at startup (KILL_SWITCH_ON_START=true). The system will not publish until explicitly disarmed by admin.
- Fail closed: If state cannot be read, assume ON (active).
- Turning the kill switch back OFF (disarming) ALWAYS requires explicit human intervention.
- Every state toggle is recorded in the append-only audit_log table.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.audit import record_audit
from app.core.clock import utc_now_iso
from app.core.logging import get_logger
from app.db.models import Incident, SystemState

logger = get_logger(__name__)

KILL_SWITCH_KEY = "kill_switch"
KILL_REASON_KEY = "kill_reason"


async def is_kill_switch_active(session: AsyncSession) -> bool:
    """Return True if kill switch is ON (publishing blocked); False if OFF (armed).

    Fail-closed: Returns True if DB error occurs or key is not found.
    """
    try:
        record = await session.scalar(
            select(SystemState).where(SystemState.key == KILL_SWITCH_KEY)
        )
        if record is None:
            # Not initialized yet — fail closed
            return True
        return record.value.strip().lower() == "on"
    except Exception as exc:
        logger.error("Failed to read kill switch state from DB — failing closed (ON)", error=str(exc))
        return True


async def get_kill_switch_status(session: AsyncSession) -> dict[str, Any]:
    """Get comprehensive kill switch status with reason and last updated timestamp."""
    try:
        ks_record = await session.scalar(
            select(SystemState).where(SystemState.key == KILL_SWITCH_KEY)
        )
        reason_record = await session.scalar(
            select(SystemState).where(SystemState.key == KILL_REASON_KEY)
        )

        active = ks_record.value.strip().lower() == "on" if ks_record else True
        reason = reason_record.value if reason_record else "System default ON at startup"
        updated_at = ks_record.updated_at if ks_record else utc_now_iso()

        return {
            "active": active,
            "status": "on" if active else "off",
            "reason": reason,
            "updated_at": updated_at,
        }
    except Exception as exc:
        logger.error("Error retrieving kill switch status", error=str(exc))
        return {
            "active": True,
            "status": "on",
            "reason": "Error checking state — fail closed",
            "updated_at": utc_now_iso(),
        }


async def set_kill_switch(
    session: AsyncSession,
    *,
    active: bool,
    reason: str,
    actor: str = "admin",
) -> dict[str, Any]:
    """Toggle the kill switch state.

    Args:
        session: Active async database session.
        active: True to engage (stop publishing); False to disarm (allow publishing).
        reason: Explanation for this state change.
        actor: Who initiated ('admin', 'system', 'telegram').

    Returns:
        Updated status dictionary.
    """
    now = utc_now_iso()
    new_value = "on" if active else "off"
    action = "kill_switch_on" if active else "kill_switch_off"

    # Update or insert kill_switch state
    ks_record = await session.scalar(
        select(SystemState).where(SystemState.key == KILL_SWITCH_KEY)
    )
    if ks_record:
        ks_record.value = new_value
        ks_record.updated_at = now
    else:
        session.add(SystemState(key=KILL_SWITCH_KEY, value=new_value, updated_at=now))

    # Update or insert kill_reason
    reason_record = await session.scalar(
        select(SystemState).where(SystemState.key == KILL_REASON_KEY)
    )
    if reason_record:
        reason_record.value = reason
        reason_record.updated_at = now
    else:
        session.add(SystemState(key=KILL_REASON_KEY, value=reason, updated_at=now))

    # If triggered automatically by system, also record an incident
    if active and actor == "system":
        incident = Incident(
            severity="critical",
            code="KILL_SWITCH_AUTO_ENGAGED",
            detail=reason,
            created_at=now,
        )
        session.add(incident)

    await session.commit()

    # Append to audit_log
    await record_audit(
        session,
        actor=actor,
        action=action,
        entity="system_state",
        entity_id=KILL_SWITCH_KEY,
        detail={"reason": reason, "active": active},
    )

    logger.warning(
        f"Kill switch changed to {new_value.upper()}",
        active=active,
        actor=actor,
        reason=reason,
    )

    return {
        "active": active,
        "status": new_value,
        "reason": reason,
        "updated_at": now,
    }


async def ensure_kill_switch_initialized(session: AsyncSession) -> None:
    """Ensure kill_switch exists in system_state at startup.

    Default is ON (active) per hard safety requirements.
    """
    ks_record = await session.scalar(
        select(SystemState).where(SystemState.key == KILL_SWITCH_KEY)
    )
    if ks_record is None:
        now = utc_now_iso()
        initial_value = "on" if settings.KILL_SWITCH_ON_START else "off"
        initial_reason = "Default ON at startup" if settings.KILL_SWITCH_ON_START else "Initial start"
        session.add(SystemState(key=KILL_SWITCH_KEY, value=initial_value, updated_at=now))
        session.add(SystemState(key=KILL_REASON_KEY, value=initial_reason, updated_at=now))
        await session.commit()

        await record_audit(
            session,
            actor="system",
            action="kill_switch_initialized",
            entity="system_state",
            entity_id=KILL_SWITCH_KEY,
            detail={"value": initial_value, "reason": initial_reason},
        )
        logger.info("Kill switch initialized in system_state", initial_value=initial_value)

