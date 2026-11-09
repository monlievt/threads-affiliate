"""app/safety — System safety, guard, rate governor, and kill switch."""

from app.safety.killswitch import (
    ensure_kill_switch_initialized,
    get_kill_switch_status,
    is_kill_switch_active,
    set_kill_switch,
)

__all__ = [
    "ensure_kill_switch_initialized",
    "get_kill_switch_status",
    "is_kill_switch_active",
    "set_kill_switch",
]
