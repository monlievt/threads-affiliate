"""tests/test_similarity.py — Tests for content similarity calculation and deduplication."""

from __future__ import annotations

import json
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now_iso
from app.db.models import Account, Draft
from app.safety.similarity import (
    calculate_similarity,
    check_content_similarity,
    check_draft_similarity_in_db,
    compute_normalized_hash,
    normalize_text,
)


def test_normalize_text() -> None:
    """Test text normalization collapses whitespace and strips emojis."""
    raw = "  Hello   World! 😊🚀 \n\n This is a TEST.  "
    normalized = normalize_text(raw)
    assert normalized == "hello world this is a test"

    # Emoji variations produce identical normalized text
    text_with_emoji = "Compact keyboard for small desks 🔥"
    text_without_emoji = "Compact keyboard for small desks"
    assert normalize_text(text_with_emoji) == normalize_text(text_without_emoji)


def test_compute_normalized_hash_deduplication() -> None:
    """Test exact match deduplication via SHA-256 normalized hash."""
    t1 = "Check out this ergonomic mouse! Link in bio. ✨"
    t2 = "  check out this   ergonomic mouse! link in bio.   "
    t3 = "A completely different post about mechanical pencils."

    hash1 = compute_normalized_hash(t1)
    hash2 = compute_normalized_hash(t2)
    hash3 = compute_normalized_hash(t3)

    assert hash1 == hash2
    assert hash1 != hash3


def test_calculate_similarity_exact_and_different() -> None:
    """Test exact matches return 100% and disparate texts return low scores."""
    exact_a = "Found this silicone pot strainer for small kitchens."
    exact_b = "Found this silicone pot strainer for small kitchens."
    assert calculate_similarity(exact_a, exact_b) == 100.0

    different_a = "Cast iron skillet maintenance guide."
    different_b = "Wireless noise cancelling headphones review."
    assert calculate_similarity(different_a, different_b) < 30.0


def test_similarity_threshold_boundary_69_vs_71() -> None:
    """Test boundary condition around the 70% threshold (e.g. 69% passes, 71% fails)."""
    base = "Found this compact silicone strainer that clips right onto standard pots."

    # High similarity (>70% match) — same core tokens with slight filler
    similar = "Found this compact silicone strainer that clips onto standard pots today."
    res_high = check_content_similarity(similar, [base], threshold=70.0)
    assert res_high.max_similarity >= 70.0
    assert res_high.passed is False

    # Low similarity (<70% match) — different subject and words
    different = "Found a heavy wooden chopping board made from acacia wood for vegetables."
    res_low = check_content_similarity(different, [base], threshold=70.0)
    assert res_low.max_similarity < 70.0
    assert res_low.passed is True


def test_check_content_similarity_corpus() -> None:
    """Test evaluating candidate against multiple historical texts."""
    corpus = [
        "Minimalist cable management clips for under-desk mounting.",
        "Stainless steel pour over coffee cone filter review.",
        "Adjustable laptop riser stand made of solid birch wood.",
    ]

    candidate = "Under-desk cable clips for clean wire management setup."
    result = check_content_similarity(candidate, corpus, threshold=70.0)

    assert result.most_similar_text == corpus[0]
    assert result.max_similarity > 40.0


@pytest.mark.asyncio
async def test_check_draft_similarity_in_db(db_session: AsyncSession) -> None:
    """Test similarity lookup against actual Drafts stored in DB."""
    # Create test account
    acc = Account(
        username="similarity_tester",
        threads_user_id="user_sim_01",
    )
    db_session.add(acc)
    await db_session.commit()

    now_iso = utc_now_iso()
    existing_text = "Ergonomic vertical mouse with silent click buttons for office workers."

    # Store published draft in DB
    draft = Draft(
        account_id=acc.id,
        kind="post",
        prompt_version="p_v1",
        llm_model="gemini-2.5-pro",
        parts=json.dumps([existing_text]),
        text_hash=compute_normalized_hash(existing_text),
        status="published",
        created_at=now_iso,
        updated_at=now_iso,
    )
    db_session.add(draft)
    await db_session.commit()

    # 1. Candidate identical to published draft -> must fail (max_similarity = 100.0)
    res_identical = await check_draft_similarity_in_db(
        db_session,
        account_id=acc.id,
        new_text=existing_text,
        threshold=70.0,
    )
    assert res_identical.passed is False
    assert res_identical.max_similarity == 100.0

    # 2. Candidate completely new -> must pass
    res_fresh = await check_draft_similarity_in_db(
        db_session,
        account_id=acc.id,
        new_text="A dual-compartment insulated bento lunchbox for meal prep.",
        threshold=70.0,
    )
    assert res_fresh.passed is True
    assert res_fresh.max_similarity < 50.0

