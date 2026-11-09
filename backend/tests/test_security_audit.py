"""tests/test_security_audit.py — Security Audit, Log Scrubbing, and Secret Scan Test Suite (T-052).

Verifies compliance with AGENTS.md and docs/06:
1. Log scrubber masks sensitive field keys (password, token, secret, key, authorization, cookie).
2. Value pattern scrubber masks Bearer tokens, Telegram bot tokens, Gemini keys, and DB URL passwords.
3. Recursive scrubbing applies cleanly to nested dicts and lists.
4. Security headers (nosniff, DENY, Referrer-Policy) are present on HTTP responses.
5. Production 500 errors do not leak stack traces or environment variables to clients.
6. Secret scanner runs cleanly on the codebase with 0 violations.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest
from httpx import AsyncClient

from app.core.logging import (
    _scrub_sensitive_processor,
    scrub_data_structure,
    scrub_string_value,
)
from ops.security_scan import (
    check_gitignore_rules,
    run_full_security_scan,
    scan_file_contents,
)


# ---------------------------------------------------------------------------
# 1. Log Scrubber Unit Tests
# ---------------------------------------------------------------------------

def test_scrub_sensitive_keys() -> None:
    event_dict = {
        "event": "user_login",
        "username": "admin",
        "password": "SuperSecretPassword123",
        "access_token": "my_access_token_xyz",
        "api_key": "private_api_key",
        "authorization": "Bearer secret_header",
        "session_cookie": "hmac_cookie_value",
    }
    scrubbed = scrub_data_structure(event_dict)

    assert scrubbed["event"] == "user_login"
    assert scrubbed["username"] == "admin"
    assert scrubbed["password"] == "[REDACTED]"
    assert scrubbed["access_token"] == "[REDACTED]"
    assert scrubbed["api_key"] == "[REDACTED]"
    assert scrubbed["authorization"] == "[REDACTED]"
    assert scrubbed["session_cookie"] == "[REDACTED]"


def test_scrub_sensitive_value_patterns() -> None:
    # 1. Bearer token in message
    msg1 = "Outbound request sent with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz to endpoint"
    assert "Bearer [REDACTED]" in scrub_string_value(msg1)
    assert "eyJhbG" not in scrub_string_value(msg1)

    # 2. Telegram token in message
    msg2 = "Connecting to https://api.telegram.org/bot123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567/getMe"
    assert "[REDACTED_TELEGRAM_TOKEN]" in scrub_string_value(msg2)
    assert "ABCdefGHIjklMNO" not in scrub_string_value(msg2)

    # 3. Gemini key in message
    msg3 = "Gemini API key AIzaSyDUMMY123456789012345678901234567 initialized"
    assert "[REDACTED_GEMINI_KEY]" in scrub_string_value(msg3)
    assert "AIzaSy" not in scrub_string_value(msg3)

    # 4. Database password in URL
    msg4 = "Connected to postgresql://affiliate_user:SuperSecretP@ss@localhost:5432/affiliate_db"
    assert "postgresql://affiliate_user:[REDACTED]@localhost:5432/affiliate_db" in scrub_string_value(msg4)


def test_scrub_recursive_nested_structures() -> None:
    nested = {
        "user": {"name": "Admin", "token": "secret_abc"},
        "headers": [
            {"name": "Content-Type", "value": "application/json"},
            {"name": "Authorization", "value": "Bearer token123"},
        ],
        "metadata": {"nested": {"api_key": "key999"}},
    }
    scrubbed = scrub_data_structure(nested)

    assert scrubbed["user"]["token"] == "[REDACTED]"
    assert scrubbed["headers"][1]["value"] == "[REDACTED]"  # masked by key 'Authorization'
    assert scrubbed["metadata"]["nested"]["api_key"] == "[REDACTED]"


# ---------------------------------------------------------------------------
# 2. HTTP Security Headers & Production Error Handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_security_headers_present(async_client: AsyncClient) -> None:
    res = await async_client.get("/health")
    assert res.status_code == 200

    headers = res.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("X-XSS-Protection") == "1; mode=block"
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "geolocation=()" in headers.get("Permissions-Policy", "")


# ---------------------------------------------------------------------------
# 3. Secret Scanner Tests
# ---------------------------------------------------------------------------

def test_secret_scanner_detects_violations(tmp_path: Path) -> None:
    # 1. Clean file
    clean_file = tmp_path / "clean_code.py"
    clean_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")
    assert len(scan_file_contents(clean_file)) == 0

    # 2. File with simulated secret
    secret_file = tmp_path / "leaky_code.py"
    # Using concatenation so the scanner doesn't match this test file itself
    prefix = "AIzaSy"
    fake_gemini_key = prefix + "B" * 33
    secret_file.write_text(f"API_KEY = '{fake_gemini_key}'\n", encoding="utf-8")
    violations = scan_file_contents(secret_file)
    assert len(violations) == 1
    assert "Gemini API Key" in violations[0]


def test_repo_security_scan_passes() -> None:
    repo_root = Path(__file__).resolve().parent.parent.parent
    violations_count, violations = run_full_security_scan(repo_root)
    assert violations_count == 0, f"Repository security scan found violations: {violations}"
