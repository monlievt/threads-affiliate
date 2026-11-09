"""app/safety/similarity.py — Content similarity and deduplication engine.

Enforces rule V-SIM:
- Text normalized hash (SHA-256) for instant duplicate detection in drafts.text_hash
- Fuzzy similarity (token_set_ratio via rapidfuzz) against posts from the last 30 days
- Configurable threshold (default: < 70% similarity allowed)
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now
from app.core.logging import get_logger
from app.db.models import Draft

logger = get_logger(__name__)

# Emoji & non-printable character pattern
EMOJI_PATTERN = re.compile(
    r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\ud83c-\ud83e][\ud000-\udfff]",
    flags=re.UNICODE,
)
PUNCTUATION_PATTERN = re.compile(r"[^\w\s]", flags=re.UNICODE)

# Try importing rapidfuzz, with difflib fallback
try:
    from rapidfuzz import fuzz

    def _token_set_ratio(s1: str, s2: str) -> float:
        return float(fuzz.token_set_ratio(s1, s2))

except ImportError:  # pragma: no cover
    def _token_set_ratio(s1: str, s2: str) -> float:
        """Fallback token set similarity using Jaccard and SequenceMatcher."""
        tokens1 = set(s1.split())
        tokens2 = set(s2.split())
        if not tokens1 or not tokens2:
            return 0.0
        intersection = tokens1.intersection(tokens2)
        union = tokens1.union(tokens2)
        jaccard = len(intersection) / len(union)
        matcher = difflib.SequenceMatcher(None, s1, s2)
        return round((jaccard * 0.5 + matcher.ratio() * 0.5) * 100.0, 1)


class SimilarityCheckResult(BaseModel):
    """Result of similarity evaluation against recent post corpus."""

    passed: bool = Field(..., description="True if max similarity is strictly below threshold.")
    max_similarity: float = Field(..., description="Highest similarity score found (0.0 to 100.0).")
    threshold: float = Field(default=70.0, description="Configured upper limit for similarity.")
    most_similar_text: str | None = Field(default=None, description="The historical post text with highest similarity.")


def normalize_text(text: str) -> str:
    """Normalize text for consistent hashing and fuzzy comparison:

    - Convert to lowercase
    - Strip emojis and non-alphanumeric punctuation
    - Collapse all whitespace (tabs, newlines) into single spaces
    - Trim leading and trailing whitespace
    """
    without_emoji = EMOJI_PATTERN.sub("", text)
    without_punct = PUNCTUATION_PATTERN.sub(" ", without_emoji)
    collapsed_spaces = " ".join(without_punct.lower().split())
    return collapsed_spaces.strip()


def compute_normalized_hash(text: str) -> str:
    """Compute SHA-256 digest of normalized text for instant exact-match deduplication."""
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def calculate_similarity(text_a: str, text_b: str) -> float:
    """Calculate fuzzy similarity percentage (0.0 to 100.0) between two texts using token set ratio."""
    norm_a = normalize_text(text_a)
    norm_b = normalize_text(text_b)
    if not norm_a and not norm_b:
        return 100.0
    if not norm_a or not norm_b:
        return 0.0
    if norm_a == norm_b:
        return 100.0
    return round(_token_set_ratio(norm_a, norm_b), 1)


def check_content_similarity(
    new_text: str,
    historical_texts: list[str],
    *,
    threshold: float = 70.0,
) -> SimilarityCheckResult:
    """Compare a new post text against a list of historical post texts.

    Args:
        new_text: Newly generated post text to check.
        historical_texts: List of past post strings.
        threshold: Max allowed similarity percentage (default: 70.0%).

    Returns:
        SimilarityCheckResult with passed=True if max_similarity < threshold.
    """
    if not historical_texts:
        return SimilarityCheckResult(
            passed=True,
            max_similarity=0.0,
            threshold=threshold,
            most_similar_text=None,
        )

    new_hash = compute_normalized_hash(new_text)
    max_score = 0.0
    closest_text: str | None = None

    for past_text in historical_texts:
        # Fast path: exact normalized hash match
        if compute_normalized_hash(past_text) == new_hash:
            return SimilarityCheckResult(
                passed=False,
                max_similarity=100.0,
                threshold=threshold,
                most_similar_text=past_text,
            )

        score = calculate_similarity(new_text, past_text)
        if score > max_score:
            max_score = score
            closest_text = past_text

    passed = max_score < threshold
    return SimilarityCheckResult(
        passed=passed,
        max_similarity=max_score,
        threshold=threshold,
        most_similar_text=closest_text,
    )


async def check_draft_similarity_in_db(
    session: AsyncSession,
    *,
    account_id: str,
    new_text: str,
    days: int = 30,
    threshold: float = 70.0,
) -> SimilarityCheckResult:
    """Fetch active and published drafts from the past N days for an account and evaluate similarity.

    Args:
        session: Active async DB session.
        account_id: Account identifier.
        new_text: Content of candidate post.
        days: Historical lookback window in days (default 30).
        threshold: Max allowed similarity percentage (default 70.0).

    Returns:
        SimilarityCheckResult.
    """
    cutoff = (utc_now() - timedelta(days=days)).isoformat()

    # Query drafts from past 30 days that are published, scheduled, approved, or pending
    stmt = (
        select(Draft.parts)
        .where(
            Draft.account_id == account_id,
            Draft.created_at >= cutoff,
            Draft.status.in_(["published", "scheduled", "approved", "pending_review"]),
        )
        .order_by(Draft.created_at.desc())
    )

    rows = (await session.scalars(stmt)).all()
    historical_texts: list[str] = []

    for parts_json in rows:
        try:
            parts = json.loads(parts_json)
            if isinstance(parts, list):
                for p in parts:
                    if isinstance(p, str) and p.strip():
                        historical_texts.append(p)
            elif isinstance(parts, str) and parts.strip():
                historical_texts.append(parts)
        except Exception:
            continue

    return check_content_similarity(new_text, historical_texts, threshold=threshold)
