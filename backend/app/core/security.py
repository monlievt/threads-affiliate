"""app/core/security.py — Authentication, session cookies, Argon2 password hashing, and CSRF protection.

Security principles:
- Argon2id password hashing via argon2-cffi
- Signed session cookies (HMAC-SHA256) with HttpOnly, SameSite=Lax, Secure (in production)
- CSRF token validation on mutation endpoints
- In-memory failed attempt tracking (5 failures → 15 minute temporary lockout)
- Zero secrets in logs
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Cookie, Header, HTTPException, Request, status

from app.config import settings
from app.core.clock import utc_now
from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Password hashing (Argon2id)
# ---------------------------------------------------------------------------
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2 hash.

    Returns True if valid, False otherwise.
    """
    try:
        return _hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, Exception):
        return False


# ---------------------------------------------------------------------------
# Session Token (HMAC-SHA256 Signed Payload)
# ---------------------------------------------------------------------------
SESSION_COOKIE_NAME = "session"
CSRF_COOKIE_NAME = "csrf_token"
SESSION_LIFETIME_SECONDS = 7 * 24 * 3600  # 7 days


def _sign(data: bytes, secret: str) -> str:
    """Compute base64-encoded HMAC-SHA256 signature."""
    sig = hmac.new(secret.encode("utf-8"), data, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode("ascii")


def create_session_token(username: str) -> tuple[str, str]:
    """Create a signed session token and associated CSRF token.

    Returns:
        (session_token, csrf_token)
    """
    now = int(time.time())
    csrf_token = str(uuid.uuid4())
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + SESSION_LIFETIME_SECONDS,
        "csrf": csrf_token,
        "jti": str(uuid.uuid4()),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("ascii")
    sig = _sign(payload_bytes, settings.SECRET_KEY)
    token = f"{payload_b64}.{sig}"
    return token, csrf_token


def decode_session_token(token: str) -> dict[str, Any] | None:
    """Verify and decode a signed session token.

    Returns payload dict if valid and unexpired; None otherwise.
    """
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, signature = parts
        payload_bytes = base64.urlsafe_b64decode(payload_b64.encode("ascii"))
        expected_sig = _sign(payload_bytes, settings.SECRET_KEY)

        if not hmac.compare_digest(signature, expected_sig):
            return None

        payload: dict[str, Any] = json.loads(payload_bytes.decode("utf-8"))
        if int(time.time()) > payload.get("exp", 0):
            return None

        return payload
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Failed Login Attempt & Lockout Tracker
# ---------------------------------------------------------------------------
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 15 * 60  # 15 minutes


class LoginAttemptTracker:
    """In-memory rate limit and temporary lockout tracker for admin login."""

    def __init__(self) -> None:
        # ip -> {"failures": count, "locked_until": timestamp}
        self._attempts: dict[str, dict[str, Any]] = {}

    def is_locked(self, identifier: str) -> tuple[bool, int]:
        """Check if an identifier (IP address) is currently locked out.

        Returns:
            (is_locked, remaining_seconds)
        """
        now = time.time()
        record = self._attempts.get(identifier)
        if not record:
            return False, 0

        locked_until = record.get("locked_until", 0)
        if now < locked_until:
            return True, int(locked_until - now)

        # Lock expired; clean up
        if locked_until > 0 and now >= locked_until:
            record["failures"] = 0
            record["locked_until"] = 0

        return False, 0

    def record_failure(self, identifier: str) -> tuple[int, bool, int]:
        """Record a failed login attempt.

        Returns:
            (failure_count, newly_locked, lockout_seconds)
        """
        now = time.time()
        record = self._attempts.setdefault(identifier, {"failures": 0, "locked_until": 0})
        record["failures"] = record.get("failures", 0) + 1

        failures = record["failures"]
        if failures >= MAX_FAILED_ATTEMPTS:
            record["locked_until"] = now + LOCKOUT_DURATION_SECONDS
            return failures, True, LOCKOUT_DURATION_SECONDS

        return failures, False, 0

    def record_success(self, identifier: str) -> None:
        """Reset failed attempts counter on successful login."""
        self._attempts.pop(identifier, None)

    def reset_for_tests(self) -> None:
        """Clear all tracking state (used in test suite)."""
        self._attempts.clear()


# Global tracker instance
login_tracker = LoginAttemptTracker()


# ---------------------------------------------------------------------------
# FastAPI Dependencies
# ---------------------------------------------------------------------------
def get_current_admin(
    request: Request,
    session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    """FastAPI dependency: require an authenticated admin session cookie."""
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    payload = decode_session_token(session)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    # Attach decoded session to request state for convenient downstream access
    request.state.admin = payload["sub"]
    request.state.csrf_token = payload["csrf"]
    return payload


def require_csrf(
    request: Request,
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    session_payload: dict[str, Any] = None,  # type: ignore[assignment]
) -> None:
    """FastAPI dependency: validate CSRF token against active session.

    Called on mutating endpoints (POST, PUT, DELETE, PATCH).
    """
    if not session_payload:
        session = request.cookies.get(SESSION_COOKIE_NAME)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        session_payload = decode_session_token(session) or {}

    expected_csrf = session_payload.get("csrf")
    if not expected_csrf or not x_csrf_token or not hmac.compare_digest(x_csrf_token, expected_csrf):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing CSRF token",
        )

