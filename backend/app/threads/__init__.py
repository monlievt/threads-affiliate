"""app/threads — Meta Threads API clients, protocols, and OAuth integration."""

from app.threads.base import PublishedPost, QuotaInfo, ThreadsClientProtocol, TokenInfo
from app.threads.client import ThreadsHttpClient
from app.threads.fake import FakeThreadsClient
from app.threads.oauth import exchange_code_for_token, get_authorization_url
from app.threads.publisher import (
    compute_text_hash,
    get_consecutive_publish_errors,
    publish_single_post,
    reconcile_in_flight_drafts,
    reset_consecutive_publish_errors,
)

__all__ = [
    "FakeThreadsClient",
    "PublishedPost",
    "QuotaInfo",
    "ThreadsClientProtocol",
    "ThreadsHttpClient",
    "TokenInfo",
    "compute_text_hash",
    "exchange_code_for_token",
    "get_authorization_url",
    "get_consecutive_publish_errors",
    "publish_single_post",
    "reconcile_in_flight_drafts",
    "reset_consecutive_publish_errors",
]
