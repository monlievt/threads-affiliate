"""app/content/llm/base.py — LLMProvider interface and exception types."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class LLMError(Exception):
    """Base exception for LLM operations."""


class LLMQuotaExceededError(LLMError):
    """Raised when the daily LLM call budget has been exhausted."""


class LLMGenerationError(LLMError):
    """Raised when LLM API generation request fails."""


class LLMInvalidJsonError(LLMError):
    """Raised when LLM returns invalid JSON that cannot be parsed after retry."""


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol defining the standard interface for LLM completions."""

    async def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.8,
    ) -> str:
        """Generate a completion text from prompt and system instructions.

        Must return raw JSON string suitable for structured parsing.
        """
        ...

