"""app/threads/oauth.py — Meta Threads OAuth token exchange flows.

Implements the 3-step OAuth handshake:
1. Authorization URL generation
2. Authorization code exchange for short-lived token
3. Short-lived token exchange for ~60-day long-lived token
"""

from __future__ import annotations

import urllib.parse
from typing import Any

import httpx

from app.config import settings
from app.core.logging import get_logger
from app.threads.base import TokenInfo

logger = get_logger(__name__)

THREADS_OAUTH_AUTHORIZE_URL = "https://threads.net/oauth/authorize"
THREADS_ACCESS_TOKEN_URL = "https://graph.threads.net/oauth/access_token"
THREADS_LONG_LIVED_TOKEN_URL = "https://graph.threads.net/access_token"

REQUIRED_SCOPES = (
    "threads_basic",
    "threads_content_publish",
    "threads_manage_replies",
    "threads_manage_insights",
    "threads_read_replies",
)


def get_authorization_url(state: str | None = None) -> str:
    """Generate the official Meta Threads OAuth authorization URL.

    The user is redirected here to grant permissions.
    """
    params = {
        "client_id": settings.THREADS_APP_ID,
        "redirect_uri": settings.THREADS_REDIRECT_URI,
        "scope": ",".join(REQUIRED_SCOPES),
        "response_type": "code",
    }
    if state:
        params["state"] = state
    return f"{THREADS_OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


async def exchange_code_for_token(code: str) -> tuple[TokenInfo, str]:
    """Exchange authorization code for a long-lived access token.

    Step 1: Exchange code for short-lived token.
    Step 2: Exchange short-lived token for long-lived (~60 days) token.

    Returns:
        (TokenInfo, user_id)
    """
    async with httpx.AsyncClient(timeout=20.0) as client:
        # Step 1: Exchange code for short-lived token
        short_resp = await client.post(
            THREADS_ACCESS_TOKEN_URL,
            data={
                "client_id": settings.THREADS_APP_ID,
                "client_secret": settings.THREADS_APP_SECRET,
                "grant_type": "authorization_code",
                "redirect_uri": settings.THREADS_REDIRECT_URI,
                "code": code,
            },
        )
        if short_resp.status_code != 200:
            logger.error("Failed to exchange OAuth code for short-lived token")
            raise ValueError(f"OAuth code exchange failed: {short_resp.text}")

        short_data = short_resp.json()
        short_token = short_data.get("access_token")
        user_id = str(short_data.get("user_id", ""))

        if not short_token or not user_id:
            raise ValueError("OAuth response missing access_token or user_id")

        # Step 2: Exchange short-lived token for long-lived token
        long_resp = await client.get(
            THREADS_LONG_LIVED_TOKEN_URL,
            params={
                "grant_type": "th_exchange_token",
                "client_secret": settings.THREADS_APP_SECRET,
                "access_token": short_token,
            },
        )
        if long_resp.status_code != 200:
            logger.error("Failed to exchange short-lived token for long-lived token")
            raise ValueError(f"Long-lived token exchange failed: {long_resp.text}")

        long_data = long_resp.json()
        long_token = long_data.get("access_token")
        expires_in = int(long_data.get("expires_in", 5184000))

        token_info = TokenInfo(
            access_token=long_token,
            token_type=long_data.get("token_type", "bearer"),
            expires_in=expires_in,
            user_id=user_id,
        )

        return token_info, user_id
