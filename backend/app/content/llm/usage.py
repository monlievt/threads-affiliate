"""app/content/llm/usage.py — Daily LLM call tracking and budget enforcement."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.clock import utc_now
from app.core.logging import get_logger
from app.content.llm.base import LLMQuotaExceededError
from app.db.models import LlmUsage

logger = get_logger(__name__)


def get_current_day_utc() -> str:
    """Return current UTC date as YYYY-MM-DD string."""
    return utc_now().strftime("%Y-%m-%d")


async def get_daily_llm_usage(
    session: AsyncSession,
    model: str,
    day: str | None = None,
) -> int:
    """Retrieve number of LLM calls made on the specified UTC day (default: today)."""
    current_day = day or get_current_day_utc()
    record = await session.scalar(
        select(LlmUsage).where(LlmUsage.day == current_day, LlmUsage.model == model)
    )
    return record.calls if record else 0


async def check_and_increment_llm_budget(
    session: AsyncSession,
    model: str,
    budget: int | None = None,
) -> int:
    """Atomically check and increment the daily LLM call count.

    Raises:
        LLMQuotaExceededError: If calls today have reached or exceeded the configured budget.

    Returns:
        The new call count for today.
    """
    effective_budget = budget if budget is not None else settings.LLM_DAILY_CALL_BUDGET
    current_day = get_current_day_utc()

    record = await session.scalar(
        select(LlmUsage).where(LlmUsage.day == current_day, LlmUsage.model == model)
    )

    if record is None:
        record = LlmUsage(day=current_day, model=model, calls=1)
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record.calls

    if record.calls >= effective_budget:
        logger.warning(
            "Daily LLM call budget reached",
            day=current_day,
            model=model,
            calls=record.calls,
            budget=effective_budget,
        )
        raise LLMQuotaExceededError(
            f"Daily LLM budget exhausted: {record.calls}/{effective_budget} calls already made today ({current_day}) for model {model}."
        )

    record.calls += 1
    await session.commit()
    await session.refresh(record)

    logger.info(
        "LLM call recorded",
        day=current_day,
        model=model,
        call_count=record.calls,
        budget=effective_budget,
    )
    return record.calls

