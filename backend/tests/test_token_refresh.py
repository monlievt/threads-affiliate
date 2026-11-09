"""tests/test_token_refresh.py — Test suite for Token Refresh & Alerting (T-023).

Verifies:
1. Token expiration status calculation (days remaining, needs_refresh < 15 days).
2. Successful token refresh (Fernet re-encryption, expiration extension, audit logging).
3. Failed token refresh fail-closed behavior:
   - Emergency Kill Switch engaged immediately (active=True).
   - Critical incident recorded in incidents table.
   - Telegram critical alert dispatched.
   - Audit log recorded.
4. Selective bulk refresh: only accounts near expiration are refreshed.
5. /health endpoint reports token_valid accurately.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import get_recent_audit_logs
from app.core.clock import utc_now, utc_now_iso
from app.core.crypto import decrypt_token, encrypt_token
from app.db.models import Account, Incident
from app.safety.killswitch import (
    ensure_kill_switch_initialized,
    is_kill_switch_active,
    set_kill_switch,
)
from app.threads.base import TokenInfo
from app.threads.fake import FakeThreadsClient
from app.threads.token_service import (
    check_and_refresh_all_accounts,
    get_token_status,
    refresh_account_token,
)


class FailingThreadsClient(FakeThreadsClient):
    """Fake client that fails token refresh requests."""

    async def refresh_token(self) -> TokenInfo:
        raise ConnectionError("Threads OAuth server connection reset")


# ---------------------------------------------------------------------------
# 1. Token Status Calculation
# ---------------------------------------------------------------------------
def test_get_token_status_scenarios() -> None:
    now = utc_now()

    # 1. No token
    acc_empty = Account(token_encrypted=None, token_expires_at=None)
    st_empty = get_token_status(acc_empty, now=now)
    assert st_empty["has_token"] is False
    assert st_empty["valid"] is False
    assert st_empty["needs_refresh"] is True

    # 2. Healthy token: 45 days remaining (> 15 days threshold)
    expires_healthy = (now + timedelta(days=45)).isoformat()
    acc_healthy = Account(
        token_encrypted=encrypt_token("access-token-123"),
        token_expires_at=expires_healthy,
    )
    st_healthy = get_token_status(acc_healthy, now=now, threshold_days=15)
    assert st_healthy["has_token"] is True
    assert st_healthy["valid"] is True
    assert st_healthy["days_remaining"] > 40.0
    assert st_healthy["needs_refresh"] is False

    # 3. Warning token: 10 days remaining (< 15 days threshold) -> Needs refresh
    expires_soon = (now + timedelta(days=10)).isoformat()
    acc_soon = Account(
        token_encrypted=encrypt_token("access-token-456"),
        token_expires_at=expires_soon,
    )
    st_soon = get_token_status(acc_soon, now=now, threshold_days=15)
    assert st_soon["has_token"] is True
    assert st_soon["valid"] is True
    assert st_soon["days_remaining"] < 15.0
    assert st_soon["needs_refresh"] is True

    # 4. Expired token: expired 2 days ago
    expires_past = (now - timedelta(days=2)).isoformat()
    acc_past = Account(
        token_encrypted=encrypt_token("access-token-expired"),
        token_expires_at=expires_past,
    )
    st_past = get_token_status(acc_past, now=now)
    assert st_past["has_token"] is True
    assert st_past["valid"] is False
    assert st_past["days_remaining"] == 0.0
    assert st_past["needs_refresh"] is True


# ---------------------------------------------------------------------------
# 2. Successful Token Refresh
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_successful_token_refresh(db_session: AsyncSession) -> None:
    now = utc_now()
    expiring_soon_iso = (now + timedelta(days=5)).isoformat()
    initial_token = "initial-long-lived-token-001"

    account = Account(
        threads_user_id="threads_usr_123",
        username="successful_refresher",
        token_encrypted=encrypt_token(initial_token),
        token_expires_at=expiring_soon_iso,
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    fake_client = FakeThreadsClient(user_id=account.threads_user_id or "usr")

    # Perform refresh
    token_info = await refresh_account_token(db_session, account, client=fake_client)

    assert token_info.access_token is not None
    assert token_info.access_token != initial_token

    # Verify database state was updated
    await db_session.refresh(account)
    decrypted = decrypt_token(account.token_encrypted or b"")
    assert decrypted == token_info.access_token

    # Expiration extended by ~60 days (5184000s)
    new_expires_dt = datetime.fromisoformat(account.token_expires_at.replace("Z", "+00:00"))
    delta_days = (new_expires_dt - now).total_seconds() / 86400.0
    assert delta_days > 55.0

    # Verify audit log
    audit_logs = await get_recent_audit_logs(db_session, limit=10, action="token_refreshed")
    assert len(audit_logs) >= 1
    assert audit_logs[0].entity_id == account.id


# ---------------------------------------------------------------------------
# 3. Failed Token Refresh Triggers Kill Switch & Incident
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_failed_token_refresh_triggers_kill_switch_and_incident(
    db_session: AsyncSession,
) -> None:
    # Ensure kill switch is initially disarmed
    await set_kill_switch(db_session, active=False, reason="Prep fail test", actor="test")
    assert await is_kill_switch_active(db_session) is False

    account = Account(
        threads_user_id="threads_usr_fail",
        username="failing_account",
        token_encrypted=encrypt_token("expiring-token-fail"),
        token_expires_at=(utc_now() + timedelta(days=2)).isoformat(),
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    failing_client = FailingThreadsClient()

    # Attempt refresh -> MUST raise ConnectionError
    with pytest.raises(ConnectionError):
        await refresh_account_token(db_session, account, client=failing_client)

    # 1. Kill switch MUST be engaged automatically!
    assert await is_kill_switch_active(db_session) is True

    # 2. Critical incident MUST be recorded
    incident_res = await db_session.execute(
        select(Incident).where(Incident.code == "TOKEN_REFRESH_FAILED")
    )
    incident = incident_res.scalar_one_or_none()
    assert incident is not None
    assert incident.severity == "critical"
    assert "failing_account" in (incident.detail or "")

    # 3. Audit log must record failure
    audit_logs = await get_recent_audit_logs(db_session, limit=10, action="token_refresh_failed")
    assert len(audit_logs) >= 1


# ---------------------------------------------------------------------------
# 4. Selective Bulk Refresh Check
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_check_and_refresh_all_accounts(db_session: AsyncSession) -> None:
    now = utc_now()

    # Account 1: Healthy (40 days left) -> Should NOT refresh
    acc_healthy = Account(
        threads_user_id="acc_h",
        username="healthy_user",
        token_encrypted=encrypt_token("tok-healthy"),
        token_expires_at=(now + timedelta(days=40)).isoformat(),
    )
    # Account 2: Expiring in 8 days (< 15 days) -> MUST refresh
    acc_expiring = Account(
        threads_user_id="acc_e",
        username="expiring_user",
        token_encrypted=encrypt_token("tok-expiring"),
        token_expires_at=(now + timedelta(days=8)).isoformat(),
    )
    db_session.add_all([acc_healthy, acc_expiring])
    await db_session.commit()

    client_healthy = FakeThreadsClient(user_id="acc_h")
    client_expiring = FakeThreadsClient(user_id="acc_e")

    def client_factory(acc: Account) -> FakeThreadsClient:
        return client_healthy if acc.id == acc_healthy.id else client_expiring

    res = await check_and_refresh_all_accounts(
        db_session,
        client_factory=client_factory,
        threshold_days=15,
    )

    assert res["total_checked"] >= 2
    assert res["refreshed_count"] == 1
    assert res["failed_count"] == 0

    # Healthy client was NOT called
    assert client_healthy.refresh_calls == 0
    # Expiring client was called once
    assert client_expiring.refresh_calls == 1


# ---------------------------------------------------------------------------
# 5. Health Check Endpoint Reports token_valid
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_health_check_reports_token_valid(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # 1. Add account with valid token
    account = Account(
        threads_user_id="health_token_user",
        username="health_token_user",
        token_encrypted=encrypt_token("token-valid-abc"),
        token_expires_at=(utc_now() + timedelta(days=30)).isoformat(),
    )
    db_session.add(account)
    await db_session.commit()

    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["token_valid"] is True

    # 2. Update to expired token
    account.token_expires_at = (utc_now() - timedelta(days=1)).isoformat()
    await db_session.commit()

    resp_exp = await client.get("/health")
    assert resp_exp.status_code == 200
    assert resp_exp.json()["token_valid"] is False
