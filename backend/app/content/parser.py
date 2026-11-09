"""app/content/parser.py — Structured output parsing and schema validation for LLM responses."""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field


class PostVariant(BaseModel):
    """A single post or thread variant returned by the LLM."""

    parts: list[str] = Field(
        ...,
        min_length=1,
        description="Text parts of the post (1 for single post, 2-4 for a thread).",
    )
    has_link: bool = Field(default=False, description="Whether this variant contains an affiliate link.")
    link_placement: Literal["in_post", "in_first_reply", "none"] = Field(
        default="none",
        description="Where the affiliate link is positioned.",
    )
    angle: str = Field(default="curation", description="Angle or creative hook summary.")
    hook_type: str = Field(
        default="observation",
        description="Type of opening hook (e.g. observation, tip, question, list).",
    )


class GenerationOutput(BaseModel):
    """Structured container holding all generated post variants."""

    variants: list[PostVariant] = Field(..., min_length=1)


def clean_json_text(raw_text: str) -> str:
    """Strip markdown code block fences and extraneous leading/trailing whitespace."""
    text = raw_text.strip()
    # Strip ```json ... ``` or ``` ... ```
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_generation_output(raw_text: str) -> GenerationOutput:
    """Parse raw LLM string completion into validated GenerationOutput.

    Raises:
        ValueError: If JSON syntax is invalid or schema validation fails.
    """
    cleaned = clean_json_text(raw_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response is not valid JSON: {exc} — Preview: {cleaned[:150]!r}") from exc

    if not isinstance(data, dict) or "variants" not in data:
        raise ValueError(f"LLM JSON missing required root key 'variants': {data}")

    try:
        return GenerationOutput.model_validate(data)
    except Exception as exc:
        raise ValueError(f"LLM output schema validation failed: {exc}") from exc
