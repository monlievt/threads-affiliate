"""app/api/auth.py — Authentication API endpoints.

Endpoints:
- POST /api/auth/login: Authenticate admin, enforce 5-failure lockout, set HttpOnly session cookie
- POST /api/auth/logout: Clear session cookie
- GET /api/auth/me: Current authenticated admin status and CSRF token
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.config import settings
from app.core.logging import get_logger
from app.core.security import (
    CSRF_COOKIE_NAME,
    MAX_FAILED_ATTEMPTS,
    SESSION_COOKIE_NAME,
    SESSION_LIFETIME_SECONDS,
    create_session_token,
    get_current_admin,
    login_tracker,
    verify_password,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """Admin login credentials."""

    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    """Successful login response."""

    status: str = "ok"
    username: str
    csrf_token: str


class MeResponse(BaseModel):
    """Authenticated user info."""

    authenticated: bool
    username: str
    csrf_token: str


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
) -> LoginResponse:
    """Authenticate administrator with rate limit and lockout enforcement.

    - 5 consecutive failed attempts lock the IP for 15 minutes.
    - Successful authentication sets HttpOnly signed session cookie.
    """
    client_ip = request.client.host if request.client else "unknown"

    # Check lockout
    is_locked, remaining_seconds = login_tracker.is_locked(client_ip)
    if is_locked:
        logger.warning(
            "Login attempt blocked by lockout",
            client_ip=client_ip,
            remaining_seconds=remaining_seconds,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Account locked. Try again in {remaining_seconds} seconds.",
        )

    # Validate credentials
    username_valid = payload.username == settings.ADMIN_USERNAME
    password_valid = verify_password(payload.password, settings.ADMIN_PASSWORD_HASH)

    if not (username_valid and password_valid):
        failures, newly_locked, lockout_sec = login_tracker.record_failure(client_ip)
        logger.warning(
            "Failed login attempt",
            client_ip=client_ip,
            username=payload.username,
            attempt=failures,
            max_attempts=MAX_FAILED_ATTEMPTS,
        )
        if newly_locked:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed login attempts ({failures}/{MAX_FAILED_ATTEMPTS}). Account locked for {lockout_sec // 60} minutes.",
            )
        remaining_attempts = MAX_FAILED_ATTEMPTS - failures
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid credentials. {remaining_attempts} attempt(s) remaining before lockout.",
        )

    # Authentication successful — reset failed attempts
    login_tracker.record_success(client_ip)
    logger.info("Admin logged in successfully", username=payload.username, client_ip=client_ip)

    # Generate signed session & CSRF tokens
    session_token, csrf_token = create_session_token(payload.username)

    # Set HttpOnly signed session cookie
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=SESSION_LIFETIME_SECONDS,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )

    # Set readable CSRF cookie (frontend reads this to send in X-CSRF-Token header)
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=SESSION_LIFETIME_SECONDS,
        httponly=False,
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )

    return LoginResponse(status="ok", username=payload.username, csrf_token=csrf_token)


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    """Log out admin by deleting session and CSRF cookies."""
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(key=CSRF_COOKIE_NAME, path="/")
    return {"status": "ok", "message": "Logged out successfully"}


@router.get("/me", response_model=MeResponse)
async def get_me(admin_session: dict[str, Any] = Depends(get_current_admin)) -> MeResponse:
    """Return currently authenticated admin user and CSRF token."""
    return MeResponse(
        authenticated=True,
        username=admin_session["sub"],
        csrf_token=admin_session["csrf"],
    )
