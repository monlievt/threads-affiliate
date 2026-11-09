"""tests/test_llm.py — Tests for LLMProvider protocol, Fake provider, Gemini adapter, and budget tracking."""

from __future__ import annotations

import json
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, patch

from app.content.llm import (
    FakeLLMProvider,
    GeminiLLMProvider,
    LLMGenerationError,
    LLMInvalidJsonError,
    LLMQuotaExceededError,
    check_and_increment_llm_budget,
    get_daily_llm_usage,
)


# ---------------------------------------------------------------------------
# 1. FakeLLMProvider Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fake_llm_default_json_output() -> None:
    """Test that FakeLLMProvider returns valid JSON matching the post schema."""
    provider = FakeLLMProvider()
    output = await provider.generate("Generate post", system="curator instructions", temperature=0.9)

    assert provider.call_count == 1
    assert provider.last_temperature == 0.9

    data = json.loads(output)
    assert "variants" in data
    assert len(data["variants"]) >= 1

    first_variant = data["variants"][0]
    assert "parts" in first_variant
    assert "has_link" in first_variant
    assert "angle" in first_variant
    assert "hook_type" in first_variant


@pytest.mark.asyncio
async def test_fake_llm_canned_responses() -> None:
    """Test using ordered canned responses."""
    resp1 = json.dumps({"variants": [{"parts": ["First post"]}]})
    resp2 = json.dumps({"variants": [{"parts": ["Second post"]}]})

    provider = FakeLLMProvider(canned_responses=[resp1, resp2])

    assert await provider.generate("p1") == resp1
    assert await provider.generate("p2") == resp2
    assert provider.call_count == 2


@pytest.mark.asyncio
async def test_fake_llm_exception_propagation() -> None:
    """Test that fail_with properly raises the specified exception."""
    provider = FakeLLMProvider(fail_with=LLMGenerationError("Simulated API failure"))

    with pytest.raises(LLMGenerationError, match="Simulated API failure"):
        await provider.generate("test prompt")


# ---------------------------------------------------------------------------
# 2. LLM Budget & Call Tracking Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_llm_budget_tracking_and_limit(db_session: AsyncSession) -> None:
    """Test daily call counting and hard budget enforcement."""
    model_name = "gemini-2.5-pro"
    test_budget = 3

    # Initial usage should be 0
    initial = await get_daily_llm_usage(db_session, model=model_name)
    assert initial == 0

    # Call 1, 2, 3 succeed
    c1 = await check_and_increment_llm_budget(db_session, model=model_name, budget=test_budget)
    assert c1 == 1

    c2 = await check_and_increment_llm_budget(db_session, model=model_name, budget=test_budget)
    assert c2 == 2

    c3 = await check_and_increment_llm_budget(db_session, model=model_name, budget=test_budget)
    assert c3 == 3

    # Call 4 must raise LLMQuotaExceededError (budget is 3)
    with pytest.raises(LLMQuotaExceededError, match="Daily LLM budget exhausted"):
        await check_and_increment_llm_budget(db_session, model=model_name, budget=test_budget)

    # Usage remains at 3
    final_usage = await get_daily_llm_usage(db_session, model=model_name)
    assert final_usage == 3


# ---------------------------------------------------------------------------
# 3. Gemini Adapter JSON Validation & Retry Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_gemini_provider_json_retry_success() -> None:
    """Test that non-JSON output on attempt 1 triggers automatic retry and succeeds if attempt 2 is valid JSON."""
    provider = GeminiLLMProvider(api_key="mock_key", model="gemini-2.5-pro")

    invalid_first_output = "Here is your JSON response: ```json {'bad': json} ```"
    valid_second_output = json.dumps({"variants": [{"parts": ["Valid post text"]}]})

    with patch.object(
        provider,
        "_call_gemini_api",
        side_effect=[invalid_first_output, valid_second_output],
    ) as mock_api:
        output = await provider.generate("Generate prompt", system="System instructions")

        assert mock_api.call_count == 2
        assert output == valid_second_output
        parsed = json.loads(output)
        assert parsed["variants"][0]["parts"] == ["Valid post text"]


@pytest.mark.asyncio
async def test_gemini_provider_json_retry_failure_raises_error() -> None:
    """Test that if both attempt 1 and retry attempt return invalid JSON, LLMInvalidJsonError is raised."""
    provider = GeminiLLMProvider(api_key="mock_key", model="gemini-2.5-pro")

    broken_output = "Not JSON at all"

    with patch.object(
        provider,
        "_call_gemini_api",
        side_effect=[broken_output, broken_output],
    ) as mock_api:
        with pytest.raises(LLMInvalidJsonError, match="Gemini failed to return valid JSON after retry"):
            await provider.generate("Generate prompt")

        assert mock_api.call_count == 2

