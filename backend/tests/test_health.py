"""tests/test_health.py — Tests for system health check endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from unittest.mock import patch


@pytest.mark.asyncio
async def test_health_check_ok(client: AsyncClient) -> None:
    """Test /health returns 200 with all required fields when DB is healthy."""
    response = await client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert data["db"] == "ok"
    assert data["kill_switch"] == "on"
    assert data["worker_heartbeat_age_sec"] is None
    assert data["token_valid"] is None
    assert data["quota_today"] is None


@pytest.mark.asyncio
async def test_health_check_db_failure(client: AsyncClient) -> None:
    """Test /health returns 503 and status 'down' when DB check fails."""
    with patch("app.api.system.check_db_connection", return_value=False):
        response = await client.get("/health")
        assert response.status_code == 503

        data = response.json()
        assert data["status"] == "down"
        assert data["db"] == "error"
        assert data["kill_switch"] == "on"

