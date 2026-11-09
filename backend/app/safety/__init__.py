"""app/safety — System safety, guard, rate governor, and kill switch."""

from app.safety.killswitch import (
    ensure_kill_switch_initialized,
    get_kill_switch_status,
    is_kill_switch_active,
    set_kill_switch,
)
from app.safety.minimal_guard import GuardDecision, check_minimal_guard

__all__ = [
    "GuardDecision",
    "check_minimal_guard",
    "ensure_kill_switch_initialized",
    "get_kill_switch_status",
    "is_kill_switch_active",
    "set_kill_switch",
]
