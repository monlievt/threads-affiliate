"""app/threads/fake.py — In-memory fake client for testing Threads interactions without real API calls."""

from __future__ import annotations

import uuid
from typing import Any

from app.threads.base import PublishedPost, QuotaInfo, ThreadsClientProtocol, TokenInfo


class FakeThreadsClient(ThreadsClientProtocol):
    """In-memory mock for Threads API.

    Features:
    - Stores created containers and published posts
    - Configurable quota and insights metrics
    - Flaky mode to simulate transient 5xx errors or network timeouts
    """

    def __init__(
        self,
        *,
        user_id: str = "fake_threads_user_123",
        username: str = "fake_affiliate_curator",
        flaky: bool = False,
    ) -> None:
        self.user_id = user_id
        self.username = username
        self.flaky = flaky

        # In-memory storage
        self.containers: dict[str, dict[str, Any]] = {}
        self.published_posts: dict[str, PublishedPost] = {}
        self.insights_data: dict[str, dict[str, int]] = {}

        # Default quota (well within 250 posts, 1000 replies)
        self.current_quota = QuotaInfo(
            quota_usage=2,
            config_quota_total=250,
            reply_quota_usage=3,
            reply_config_total=1000,
        )

        # Call counters
        self.create_container_calls = 0
        self.publish_calls = 0
        self.refresh_calls = 0
        self._flaky_counter = 0

    def _maybe_trigger_flake(self) -> None:
        """Simulate a transient network or server error if flaky mode is enabled."""
        if self.flaky:
            self._flaky_counter += 1
            if self._flaky_counter % 2 == 1:
                raise ConnectionError("Simulated transient connection timeout or 503 Service Unavailable")

    async def create_text_container(
        self,
        text: str,
        *,
        reply_to_id: str | None = None,
        link_attachment: str | None = None,
    ) -> str:
        self._maybe_trigger_flake()
        self.create_container_calls += 1

        creation_id = f"c_{uuid.uuid4().hex[:12]}"
        self.containers[creation_id] = {
            "text": text,
            "reply_to_id": reply_to_id,
            "link_attachment": link_attachment,
            "published": False,
        }
        return creation_id

    async def publish(self, creation_id: str) -> PublishedPost:
        self._maybe_trigger_flake()
        self.publish_calls += 1

        if creation_id not in self.containers:
            raise ValueError(f"Container ID {creation_id} not found")

        container = self.containers[creation_id]
        if container.get("published"):
            # Return existing published post to ensure idempotency
            for post in self.published_posts.values():
                if post.creation_id == creation_id:
                    return post

        media_id = f"th_post_{uuid.uuid4().hex[:10]}"
        permalink = f"https://threads.net/@{self.username}/post/{media_id}"

        post = PublishedPost(
            media_id=media_id,
            permalink=permalink,
            creation_id=creation_id,
        )

        container["published"] = True
        self.published_posts[media_id] = post
        self.current_quota.quota_usage += 1
        return post

    async def get_insights(self, media_id: str) -> dict[str, int]:
        self._maybe_trigger_flake()
        if media_id in self.insights_data:
            return self.insights_data[media_id]

        # Return realistic default metrics
        return {
            "views": 150,
            "likes": 12,
            "replies": 3,
            "reposts": 2,
            "quotes": 0,
        }

    async def publishing_limit(self) -> QuotaInfo:
        self._maybe_trigger_flake()
        return self.current_quota

    async def refresh_token(self) -> TokenInfo:
        self._maybe_trigger_flake()
        self.refresh_calls += 1
        return TokenInfo(
            access_token=f"refreshed_long_lived_token_{uuid.uuid4().hex[:16]}",
            token_type="bearer",
            expires_in=5184000,
            user_id=self.user_id,
        )

