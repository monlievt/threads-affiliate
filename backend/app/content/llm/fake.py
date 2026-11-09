"""app/content/llm/fake.py — In-memory fake LLM provider for deterministic offline testing."""

from __future__ import annotations

import json
from typing import Any

from app.content.llm.base import LLMGenerationError, LLMProvider

DEFAULT_FAKE_COMPLETION = json.dumps({
    "variants": [
        {
            "parts": [
                "Found this compact silicone strainer that clips right onto standard pots. Saves kitchen cabinet space! Affiliate link: https://benable.com/kitchen/clip"
            ],
            "has_link": True,
            "link_placement": "in_post",
            "angle": "space saving utility",
            "hook_type": "observation",
        },
        {
            "parts": [
                "If you prep meals in a small kitchen, this clip-on silicone strainer caught my eye. No bulky colander needed. Affiliate link: https://benable.com/kitchen/clip"
            ],
            "has_link": True,
            "link_placement": "in_post",
            "angle": "minimalist prep",
            "hook_type": "tip",
        },
    ]
})


class FakeLLMProvider(LLMProvider):
    """Mock LLM implementation for tests without external network or API keys."""

    def __init__(
        self,
        canned_responses: list[str] | None = None,
        fail_with: Exception | None = None,
    ) -> None:
        self.canned_responses = list(canned_responses) if canned_responses else []
        self.fail_with = fail_with
        self.call_count = 0
        self.last_prompt = ""
        self.last_system = ""
        self.last_temperature = 0.8

    async def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.8,
    ) -> str:
        self.call_count += 1
        self.last_prompt = prompt
        self.last_system = system
        self.last_temperature = temperature

        if self.fail_with:
            raise self.fail_with

        if self.canned_responses:
            return self.canned_responses.pop(0)

        return DEFAULT_FAKE_COMPLETION
