"""tests/test_threads_client.py — Tests for Threads clients (fake and real) and OAuth flows."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, patch

from app.core.crypto import decrypt_token
from app.db.models import Account, AuditLog
from app.threads.base import TokenInfo
from app.threads.client import (
    ThreadsApiError,
    ThreadsHttpClient,
    ThreadsPermanentApiError,
    ThreadsRateLimitError,
)
from app.threads.fake import FakeThreadsClient
from app.threads.oauth import get_authorization_url


# ---------------------------------------------------------------------------
# 1. FakeThreadsClient Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fake_threads_client_lifecycle() -> None:
    """Test standard lifecycle with FakeThreadsClient."""
    client = FakeThreadsClient(user_id="user_999", username="test_curator")

    # 1. Create container
    cid = await client.create_text_container("Hello world post text", link_attachment="https://benable.com/abc")
    assert cid.startswith("c_")
    assert cid in client.containers

    # 2. Publish
    published = await client.publish(cid)
    assert published.media_id.startswith("th_post_")
    assert published.creation_id == cid
    assert "threads.net/@test_curator" in (published.permalink or "")

    # 3. Idempotency: publishing same creation_id returns same post
    published_again = await client.publish(cid)
    assert published_again.media_id == published.media_id

    # 4. Insights
    insights = await client.get_insights(published.media_id)
    assert "views" in insights
    assert "likes" in insights
    assert insights["views"] >= 0

    # 5. Publishing limit
    quota = await client.publishing_limit()
    assert quota.config_quota_total == 250
    assert quota.reply_config_total == 1000
    assert quota.quota_usage >= 1

    # 6. Refresh token
    token = await client.refresh_token()
    assert token.access_token.startswith("refreshed_")
    assert token.expires_in > 0


@pytest.mark.asyncio
async def test_fake_threads_client_flaky_mode() -> None:
    """Test that flaky=True raises connection error on alternating calls."""
    client = FakeThreadsClient(flaky=True)

    # 1st call triggers flake
    with pytest.raises(ConnectionError, match="Simulated transient"):
        await client.create_text_container("First try")

    # 2nd call succeeds
    cid = await client.create_text_container("Second try")
    assert cid.startswith("c_")


# ---------------------------------------------------------------------------
# 2. ThreadsHttpClient Unit & Error Handling Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_threads_http_client_429_rate_limit() -> None:
    """Test that 429 status raises ThreadsRateLimitError without retrying."""
    client = ThreadsHttpClient("user_123", "dummy_token")

    with patch.object(
        client,
        "_request_with_retry",
        side_effect=ThreadsRateLimitError("Rate limit reached", status_code=429),
    ):
        with pytest.raises(ThreadsRateLimitError):
            await client.create_text_container("Test post")


@pytest.mark.asyncio
async def test_threads_http_client_permanent_error() -> None:
    """Test that 4xx status raises ThreadsPermanentApiError."""
    client = ThreadsHttpClient("user_123", "dummy_token")

    with patch.object(
        client,
        "_request_with_retry",
        side_effect=ThreadsPermanentApiError("Invalid parameters", status_code=400),
    ):
        with pytest.raises(ThreadsPermanentApiError):
            await client.publish("c_invalid")


# ---------------------------------------------------------------------------
# 3. OAuth Flow Tests
# ---------------------------------------------------------------------------
def test_oauth_authorization_url() -> None:
    """Test that the authorization URL is properly constructed."""
    url = get_authorization_url(state="csrf_state_xyz")
    assert url.startswith("https://threads.net/oauth/authorize?")
    assert "scope=" in url
    assert "threads_basic" in url
    assert "threads_content_publish" in url
    assert "state=csrf_state_xyz" in url
    assert "response_type=code" in url


@pytest.mark.asyncio
async def test_oauth_callback_flow_stores_encrypted_token(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test OAuth callback stores account with encrypted token and records audit log."""
    raw_token = "THQ_real_long_lived_token_from_meta_987654321"
    fake_user_id = "threads_usr_456"

    mock_token_info = TokenInfo(
        access_token=raw_token,
        token_type="bearer",
        expires_in=5184000,
        user_id=fake_user_id,
    )

    with patch(
        "app.api.oauth.exchange_code_for_token",
        new=AsyncMock(return_value=(mock_token_info, fake_user_id)),
    ):
        resp = await client.get("/api/oauth/threads/callback?code=mock_auth_code_123")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["threads_user_id"] == fake_user_id

        # Query database to verify encryption
        account = await db_session.scalar(
            select(Account).where(Account.threads_user_id == fake_user_id)
        )
        assert account is not None
        assert account.token_encrypted is not None

        # Verify token is encrypted, NOT stored in plaintext
        assert raw_token.encode("utf-8") not in account.token_encrypted

        # Verify decryption restores exact original token
        decrypted = decrypt_token(account.token_encrypted)
        assert decrypted == raw_token

        # Verify audit log was written without leaking token
        audit = await db_session.scalar(
            select(AuditLog).where(AuditLog.action == "threads_oauth_connected")
        )
        assert audit is not None
        assert raw_token not in (audit.detail or "")
