"""tests/test_crypto_audit_killswitch.py — Tests for crypto, audit log, and kill switch."""

from __future__ import annotations

import json
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import get_recent_audit_logs, record_audit
from app.core.crypto import decrypt_token, encrypt_token, generate_encryption_key
from app.core.security import SESSION_COOKIE_NAME, create_session_token
from app.db.models import AuditLog, SystemState
from app.safety.killswitch import (
    ensure_kill_switch_initialized,
    get_kill_switch_status,
    is_kill_switch_active,
    set_kill_switch,
)


# ---------------------------------------------------------------------------
# 1. Token Crypto Tests
# ---------------------------------------------------------------------------
def test_token_encryption_roundtrip() -> None:
    """Test encrypting and decrypting a Threads OAuth token."""
    raw_token = "THQ_oauth_test_token_long_string_abc123!@#"
    ciphertext = encrypt_token(raw_token)

    assert isinstance(ciphertext, bytes)
    assert ciphertext != raw_token.encode("utf-8")
    assert raw_token.encode("utf-8") not in ciphertext

    decrypted = decrypt_token(ciphertext)
    assert decrypted == raw_token


def test_empty_token_encryption() -> None:
    """Test encrypting and decrypting empty token returns empty values."""
    assert encrypt_token("") == b""
    assert decrypt_token(b"") == ""


def test_decrypt_corrupted_token_raises_value_error() -> None:
    """Test that tampering with ciphertext causes decrypt_token to raise ValueError."""
    ciphertext = encrypt_token("some_token")
    corrupted = ciphertext[:-5] + b"XXXXX"

    with pytest.raises(ValueError, match="Decryption failed"):
        decrypt_token(corrupted)


def test_generate_encryption_key() -> None:
    """Test generating a random Fernet key."""
    key = generate_encryption_key()
    assert isinstance(key, str)
    assert len(key) == 44  # 32 bytes base64-encoded is 44 chars


# ---------------------------------------------------------------------------
# 2. Audit Log Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_audit_log_append_and_scrubbing(db_session: AsyncSession) -> None:
    """Test recording an audit log and ensuring sensitive fields are scrubbed."""
    entry = await record_audit(
        db_session,
        actor="admin",
        action="update_credentials",
        entity="account",
        entity_id="acc_123",
        detail={
            "username": "monliev",
            "threads_token": "secret-token-value-should-be-hidden",
            "admin_password": "supersecretpassword",
            "safe_param": "regular_value",
        },
    )

    assert entry.id is not None
    assert entry.actor == "admin"
    assert entry.action == "update_credentials"

    detail = json.loads(entry.detail or "{}")
    assert detail["threads_token"] == "[REDACTED]"
    assert detail["admin_password"] == "[REDACTED]"
    assert detail["safe_param"] == "regular_value"
    assert detail["username"] == "monliev"

    # Verify query
    logs = await get_recent_audit_logs(db_session, action="update_credentials")
    assert len(logs) == 1
    assert logs[0].id == entry.id


# ---------------------------------------------------------------------------
# 3. Kill Switch Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_kill_switch_default_on(db_session: AsyncSession) -> None:
    """Test that kill switch initializes to ON (active)."""
    await ensure_kill_switch_initialized(db_session)

    active = await is_kill_switch_active(db_session)
    assert active is True

    status = await get_kill_switch_status(db_session)
    assert status["active"] is True
    assert status["status"] == "on"
    assert "Default ON" in status["reason"]


@pytest.mark.asyncio
async def test_kill_switch_toggle_and_audit(db_session: AsyncSession) -> None:
    """Test disarming and re-arming kill switch, verifying DB records and audit log."""
    await ensure_kill_switch_initialized(db_session)

    # Disarm (active=False) by admin
    res_off = await set_kill_switch(
        db_session,
        active=False,
        reason="Manual operator approval to start test publishing",
        actor="admin",
    )
    assert res_off["active"] is False
    assert res_off["status"] == "off"

    active_now = await is_kill_switch_active(db_session)
    assert active_now is False

    # Check audit log for kill_switch_off
    logs_off = await get_recent_audit_logs(db_session, action="kill_switch_off")
    assert len(logs_off) >= 1
    assert logs_off[0].actor == "admin"

    # Re-engage (active=True)
    res_on = await set_kill_switch(
        db_session,
        active=True,
        reason="Emergency pause triggered",
        actor="admin",
    )
    assert res_on["active"] is True
    assert res_on["status"] == "on"

    active_again = await is_kill_switch_active(db_session)
    assert active_again is True

    # Check audit log for kill_switch_on
    logs_on = await get_recent_audit_logs(db_session, action="kill_switch_on")
    assert len(logs_on) >= 1


# ---------------------------------------------------------------------------
# 4. Kill Switch API Endpoint Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_kill_switch_api_endpoints(client: AsyncClient, db_session: AsyncSession) -> None:
    """Test GET and POST /api/system/kill-switch endpoints."""
    await ensure_kill_switch_initialized(db_session)

    token, csrf = create_session_token("admin")
    client.cookies.set(SESSION_COOKIE_NAME, token)

    # GET status
    resp_get = await client.get("/api/system/kill-switch")
    assert resp_get.status_code == 200
    data = resp_get.json()
    assert data["active"] is True
    assert data["status"] == "on"

    # POST toggle without CSRF should be 403 Forbidden
    resp_no_csrf = await client.post(
        "/api/system/kill-switch",
        json={"active": False, "reason": "Operator arming system"},
    )
    assert resp_no_csrf.status_code == 403

    # POST toggle with valid CSRF should succeed
    resp_toggle = await client.post(
        "/api/system/kill-switch",
        json={"active": False, "reason": "Operator arming system"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp_toggle.status_code == 200
    res_data = resp_toggle.json()
    assert res_data["active"] is False
    assert res_data["status"] == "off"

    # Verify public /health reflects new kill switch status
    resp_health = await client.get("/health")
    assert resp_health.status_code == 200
    assert resp_health.json()["kill_switch"] == "off"
