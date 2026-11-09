"""app/content/llm/gemini.py — Google Gemini Pro LLM adapter using google-genai SDK.

Features:
- Gemini 2.5 Pro (paid tier per BRD §5 & docs/05 §3) for zero-training data privacy
- Forces JSON output format (response_mime_type="application/json")
- Automatic single retry if initial completion returns non-valid JSON
- Zero API keys in logs
"""

from __future__ import annotations

import json
from typing import Any

from app.config import settings
from app.core.logging import get_logger
from app.content.llm.base import (
    LLMGenerationError,
    LLMInvalidJsonError,
    LLMProvider,
)

logger = get_logger(__name__)


class GeminiLLMProvider(LLMProvider):
    """Adapter for Google Gemini API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL_TEXT

    async def _call_gemini_api(
        self,
        prompt: str,
        system: str,
        temperature: float,
    ) -> str:
        """Execute single raw call to Gemini API using google-genai SDK."""
        if not self.api_key:
            raise LLMGenerationError("GEMINI_API_KEY is not configured.")

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)

            config = types.GenerateContentConfig(
                temperature=temperature,
                response_mime_type="application/json",
                system_instruction=system if system else None,
            )

            # In google-genai SDK: client.aio.models.generate_content for async
            response = await client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )

            text_output = response.text or ""
            return text_output.strip()

        except Exception as exc:
            logger.error("Gemini API generation request failed", model=self.model, error=str(exc))
            raise LLMGenerationError(f"Gemini API request failed: {exc}") from exc

    async def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.8,
    ) -> str:
        """Generate structured JSON completion with 1x automatic retry on invalid JSON."""
        # Attempt 1
        raw_output = await self._call_gemini_api(prompt, system, temperature)

        try:
            json.loads(raw_output)
            return raw_output
        except json.JSONDecodeError:
            logger.warning("Gemini returned non-JSON output on attempt 1. Retrying with strict JSON instruction.")

        # Attempt 2 (Retry 1x with strict reinforcement)
        strict_system = (
            (system + "\n\n" if system else "")
            + "CRITICAL: Return ONLY raw, valid JSON matching the exact schema. No markdown fences, no explanatory text."
        )
        retry_output = await self._call_gemini_api(prompt, strict_system, temperature)

        try:
            json.loads(retry_output)
            return retry_output
        except json.JSONDecodeError as exc:
            logger.error("Gemini returned invalid JSON on second attempt", raw_preview=retry_output[:100])
            raise LLMInvalidJsonError(
                f"Gemini failed to return valid JSON after retry: {retry_output[:200]}"
            ) from exc
