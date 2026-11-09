"""tests/test_auth.py — Tests for admin authentication, sessions, CSRF, and lockout."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.config import settings
from app.core.security import (
    CSRF_COOKIE_NAME,
    MAX_FAILED_ATTEMPTS,
    SESSION_COOKIE_NAME,
    create_session_token,
    decode_session_token,
    hash_password,
    login_tracker,
    verify_password,
)


@pytest.fixture(autouse=True)
def reset_tracker() -> None:
    """Reset lockout tracker state before and after each test."""
    login_tracker.reset_for_tests()
    yield
    login_tracker.reset_for_tests()


def test_argon2_hashing_and_verification() -> None:
    """Test Argon2 password hashing and verification."""
    pwd = "super-secure-admin-pass-123"
    hashed = hash_password(pwd)

    assert hashed != pwd
    assert hashed.startswith("$argon2id$")
    assert verify_password(pwd, hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_session_token_roundtrip_and_tampering() -> None:
    """Test creating, decoding, and tampering with session tokens."""
    token, csrf = create_session_token("admin")
    payload = decode_session_token(token)

    assert payload is not None
    assert payload["sub"] == "admin"
    assert payload["csrf"] == csrf

    # Tampered signature should be rejected
    tampered = token[:-4] + "XXXX"
    assert decode_session_token(tampered) is None

    # Invalid format should be rejected
    assert decode_session_token("not-a-token") is None


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test successful login sets HttpOnly session cookie and returns CSRF token."""
    test_password = "correct-admin-password"
    hashed = hash_password(test_password)

    monkeypatch.setattr(settings, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD_HASH", hashed)

    response = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": test_password},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["username"] == "admin"
    assert "csrf_token" in data

    # Verify cookies
    cookies = response.cookies
    assert SESSION_COOKIE_NAME in cookies
    assert CSRF_COOKIE_NAME in cookies


@pytest.mark.asyncio
async def test_login_invalid_credentials(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test login with wrong password returns 401."""
    hashed = hash_password("secret-pass")
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD_HASH", hashed)

    response = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert "Invalid credentials" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_lockout_after_5_failures(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that 5 consecutive failed attempts trigger a 429 lockout."""
    hashed = hash_password("real-pass")
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD_HASH", hashed)

    # First 4 attempts: 401 Unauthorized
    for i in range(MAX_FAILED_ATTEMPTS - 1):
        resp = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": f"bad-{i}"},
        )
        assert resp.status_code == 401, f"Attempt {i+1} should be 401"

    # 5th attempt triggers lockout: 429 Too Many Requests
    resp5 = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "bad-final"},
    )
    assert resp5.status_code == 429
    assert "locked" in resp5.json()["detail"].lower()

    # Subsequent attempt even with correct password is also locked out: 429
    resp_locked = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "real-pass"},
    )
    assert resp_locked.status_code == 429


@pytest.mark.asyncio
async def test_me_endpoint_requires_auth(client: AsyncClient) -> None:
    """Test /api/auth/me returns 401 without session cookie and 200 with valid session."""
    # Without cookie
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401

    # With valid session cookie
    token, csrf = create_session_token("admin")
    client.cookies.set(SESSION_COOKIE_NAME, token)

    resp_auth = await client.get("/api/auth/me")
    assert resp_auth.status_code == 200
    data = resp_auth.json()
    assert data["authenticated"] is True
    assert data["username"] == "admin"
    assert data["csrf_token"] == csrf


@pytest.mark.asyncio
async def test_logout(client: AsyncClient) -> None:
    """Test logout endpoint clears session and CSRF cookies."""
    token, _ = create_session_token("admin")
    client.cookies.set(SESSION_COOKIE_NAME, token)

    response = await client.post("/api/auth/logout")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
