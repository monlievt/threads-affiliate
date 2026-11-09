"""app/threads/client.py — Official Meta Threads API HTTP Client.

Features:
- Official endpoints per docs/05-INTEGRATIONS.md §1
- Strict token scrubbing: Tokens are never written to logs or error messages
- Retry policy: Retries up to 3 times on 5xx and timeouts with exponential backoff
- Fail-fast on 4xx client errors (429 rate limit triggers immediate stop)
- 20-second request timeout
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx

from app.config import settings
from app.core.logging import get_logger
from app.threads.base import PublishedPost, QuotaInfo, ThreadsClientProtocol, TokenInfo

logger = get_logger(__name__)


class ThreadsApiError(Exception):
    """Base exception for Threads API errors."""

    def __init__(self, message: str, status_code: int | None = None, response_body: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class ThreadsRateLimitError(ThreadsApiError):
    """Raised when Threads API returns 429 Too Many Requests."""


class ThreadsPermanentApiError(ThreadsApiError):
    """Raised on non-retryable 4xx client errors (e.g., 400 Bad Request, 403 Forbidden)."""


class ThreadsHttpClient(ThreadsClientProtocol):
    """HTTP client communicating with the Meta Threads API."""

    def __init__(
        self,
        user_id: str,
        access_token: str,
        *,
        base_url: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.user_id = user_id
        self._access_token = access_token
        self.base_url = (base_url or settings.THREADS_API_BASE).rstrip("/")
        self.timeout = timeout

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """Execute HTTP request with exponential backoff retry on 5xx / timeout."""
        headers = self._get_headers()
        attempt = 0

        while True:
            attempt += 1
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.request(
                        method,
                        url,
                        headers=headers,
                        params=params,
                        data=data,
                    )

                # Success
                if resp.status_code in (200, 201):
                    return resp.json()

                # Handle 429 Rate Limit
                if resp.status_code == 429:
                    logger.warning("Threads API returned 429 Rate Limit", status_code=429)
                    raise ThreadsRateLimitError(
                        "Threads API rate limit reached (429)",
                        status_code=429,
                        response_body=resp.text,
                    )

                # Handle 4xx Client Errors (do NOT retry)
                if 400 <= resp.status_code < 500:
                    logger.error(
                        "Threads API client error (non-retryable)",
                        status_code=resp.status_code,
                    )
                    raise ThreadsPermanentApiError(
                        f"Threads API permanent error {resp.status_code}: {resp.text}",
                        status_code=resp.status_code,
                        response_body=resp.text,
                    )

                # 5xx Server Errors (retryable)
                if attempt > max_retries:
                    raise ThreadsApiError(
                        f"Threads API server error {resp.status_code} after {max_retries} retries",
                        status_code=resp.status_code,
                    )

            except (httpx.TimeoutException, httpx.NetworkError, ThreadsApiError) as exc:
                if isinstance(exc, (ThreadsRateLimitError, ThreadsPermanentApiError)):
                    raise

                if attempt > max_retries:
                    logger.error("Threads API request exhausted all retries", error=str(exc))
                    raise ThreadsApiError(f"Threads API request failed after {max_retries} retries: {exc}") from exc

            # Backoff with jitter: 1s, 2s, 4s...
            backoff = (2 ** (attempt - 1)) + random.uniform(0.1, 0.5)
            logger.warning("Retrying Threads API request after backoff", attempt=attempt, backoff=backoff)
            await asyncio.sleep(backoff)

    async def create_text_container(
        self,
        text: str,
        *,
        reply_to_id: str | None = None,
        link_attachment: str | None = None,
    ) -> str:
        """Create a text container via POST /{user-id}/threads."""
        url = f"{self.base_url}/{self.user_id}/threads"
        data: dict[str, Any] = {
            "media_type": "TEXT",
            "text": text,
        }
        if reply_to_id:
            data["reply_to_id"] = reply_to_id
        if link_attachment:
            data["link_attachment"] = link_attachment

        result = await self._request_with_retry("POST", url, data=data)
        creation_id = str(result.get("id"))
        if not creation_id:
            raise ThreadsApiError("Response missing container creation ID", response_body=result)
        return creation_id

    async def publish(self, creation_id: str) -> PublishedPost:
        """Publish a container via POST /{user-id}/threads_publish."""
        url = f"{self.base_url}/{self.user_id}/threads_publish"
        data = {"creation_id": creation_id}

        result = await self._request_with_retry("POST", url, data=data)
        media_id = str(result.get("id"))
        if not media_id:
            raise ThreadsApiError("Response missing media ID", response_body=result)

        permalink = result.get("permalink")
        return PublishedPost(
            media_id=media_id,
            permalink=permalink,
            creation_id=creation_id,
        )

    async def get_insights(self, media_id: str) -> dict[str, int]:
        """Fetch post insights via GET /{media-id}/insights."""
        url = f"{self.base_url}/{media_id}/insights"
        params = {"metric": "views,likes,replies,reposts,quotes"}

        result = await self._request_with_retry("GET", url, params=params)
        metrics: dict[str, int] = {
            "views": 0,
            "likes": 0,
            "replies": 0,
            "reposts": 0,
            "quotes": 0,
        }

        data_list = result.get("data", [])
        for item in data_list:
            name = item.get("name")
            values = item.get("values", [])
            val = values[0].get("value", 0) if values else 0
            if name in metrics:
                metrics[name] = int(val)

        return metrics

    async def publishing_limit(self) -> QuotaInfo:
        """Fetch quota limits via GET /{user-id}/threads_publishing_limit."""
        url = f"{self.base_url}/{self.user_id}/threads_publishing_limit"
        params = {"fields": "quota_usage,config,reply_quota_usage,reply_config"}

        result = await self._request_with_retry("GET", url, params=params)
        data_list = result.get("data", [{}])
        info = data_list[0] if data_list else {}

        config_data = info.get("config", {})
        reply_config_data = info.get("reply_config", {})

        return QuotaInfo(
            quota_usage=int(info.get("quota_usage", 0)),
            config_quota_total=int(config_data.get("quota_total", 250)),
            reply_quota_usage=int(info.get("reply_quota_usage", 0)),
            reply_config_total=int(reply_config_data.get("quota_total", 1000)),
        )

    async def refresh_token(self) -> TokenInfo:
        """Refresh long-lived access token via GET https://graph.threads.net/refresh_access_token."""
        url = "https://graph.threads.net/refresh_access_token"
        params = {
            "grant_type": "th_refresh_token",
            "access_token": self._access_token,
        }

        # Custom call to avoid logging access_token query param
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params)
            if resp.status_code != 200:
                raise ThreadsApiError(
                    f"Token refresh failed: HTTP {resp.status_code}",
                    status_code=resp.status_code,
                )
            data = resp.json()
            return TokenInfo(
                access_token=data["access_token"],
                token_type=data.get("token_type", "bearer"),
                expires_in=int(data.get("expires_in", 5184000)),
                user_id=self.user_id,
            )
        except Exception as exc:
            logger.error("Failed to refresh Threads long-lived token")
            raise ThreadsApiError("Token refresh network request failed") from exc
