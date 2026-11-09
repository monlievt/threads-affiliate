"""app/threads/base.py — Interfaces and data transfer objects for Meta Threads API."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from pydantic import BaseModel, Field


class PublishedPost(BaseModel):
    """Result of publishing a container to Threads."""

    media_id: str = Field(..., description="Threads media ID of the published post.")
    permalink: str | None = Field(default=None, description="Public permalink URL to the post.")
    creation_id: str | None = Field(default=None, description="The container creation ID used.")


class QuotaInfo(BaseModel):
    """Publishing and reply quota information from Threads API."""

    quota_usage: int = Field(default=0, description="Posts published in current 24h rolling window.")
    config_quota_total: int = Field(default=250, description="Max allowed posts per 24h (API limit is 250).")
    reply_quota_usage: int = Field(default=0, description="Replies published in current 24h window.")
    reply_config_total: int = Field(default=1000, description="Max allowed replies per 24h (API limit is 1000).")


class TokenInfo(BaseModel):
    """OAuth access token details."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(default=5184000, description="Remaining seconds (approx 60 days).")
    user_id: str | None = None


@runtime_checkable
class ThreadsClientProtocol(Protocol):
    """Protocol defining the interface for interacting with Threads API."""

    async def create_text_container(
        self,
        text: str,
        *,
        reply_to_id: str | None = None,
        link_attachment: str | None = None,
    ) -> str:
        """Create a text media container. Returns creation_id."""
        ...

    async def publish(self, creation_id: str) -> PublishedPost:
        """Publish a previously created container. Returns PublishedPost."""
        ...

    async def get_insights(self, media_id: str) -> dict[str, int]:
        """Fetch views, likes, replies, reposts, quotes for a given post."""
        ...

    async def publishing_limit(self) -> QuotaInfo:
        """Fetch current publishing and reply quota limits and usage."""
        ...

    async def refresh_token(self) -> TokenInfo:
        """Refresh long-lived access token before expiration."""
        ...
