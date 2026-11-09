"""app/core/clock.py — Time utilities.

All times stored in DB are UTC. Display times use Asia/Jakarta.
"""

from __future__ import annotations

from datetime import datetime, timezone, tzinfo

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-reattr,import-not-found]

JAKARTA_TZ: tzinfo = ZoneInfo("Asia/Jakarta")
UTC_TZ: tzinfo = timezone.utc


def utc_now() -> datetime:
    """Return current time as UTC-aware datetime."""
    return datetime.now(tz=UTC_TZ)


def to_jakarta(dt: datetime) -> datetime:
    """Convert a UTC datetime to Asia/Jakarta timezone for display."""
    if dt.tzinfo is None:
        # Assume naive datetimes are UTC
        dt = dt.replace(tzinfo=UTC_TZ)
    return dt.astimezone(JAKARTA_TZ)


def format_jakarta(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S WIB") -> str:
    """Format a datetime in Asia/Jakarta timezone as a human-readable string."""
    return to_jakarta(dt).strftime(fmt)


def utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return utc_now().isoformat()
