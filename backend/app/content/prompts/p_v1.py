"""app/content/prompts/p_v1.py — System prompt template version p_v1.

Follows strict guidelines from docs/07-CONTENT-EXPERIMENT.md §4.3:
- Enforces tone rules and humble curator voice
- Strictly forbids prices, discounts, fake personal experience, medical claims, urgency
- Disallows recent openers to maintain fresh variety
- Outputs strict JSON matching schema
"""

from __future__ import annotations

import json
from typing import Any

from app.db.models import Niche, Persona, Product, Style

PROMPT_VERSION = "p_v1"


def build_p_v1_prompt(
    *,
    persona: Persona,
    style: Style,
    niche: Niche,
    product: Product | None = None,
    country: str = "US",
    recent_openers: list[str] | None = None,
    num_variants: int = 3,
) -> tuple[str, str]:
    """Construct system instructions and user prompt for template p_v1.

    Returns:
        (system_instruction, user_prompt)
    """
    recent_openers_formatted = (
        ", ".join([f'"{op}"' for op in recent_openers[:10]])
        if recent_openers
        else "None"
    )

    disclosure_text = persona.disclosure_text or "Affiliate link"
    disclosure_position = persona.disclosure_position or "end"

    system_instruction = f"""You write short Threads posts for an English-speaking audience in {country}.
Persona voice: {persona.voice}
Avoid completely: {persona.avoid or 'Generic hype, marketing fluff, excessive emojis'}
Style: {style.name} — {style.tone_rules}
Max {style.max_chars} characters per post part.

Hard Rules (MUST FOLLOW STRICTLY):
- Never state prices, currency amounts, discounts, % off, sale, clearance, or stock claims.
- Never claim personal use or hands-on testing experience with the product. Frame as discovery, curation, or general tips.
- No medical or health claims. No guaranteed results.
- No false urgency ("ends tonight", "hurry before it's gone", "only 3 left").
- No engagement baiting ("follow to win", "tag a friend"). Max 2 hashtags. No @mentions.
- Do NOT start any post with any of these recently used openers: [{recent_openers_formatted}].
- Sound like a thoughtful human curator, not a marketer. Vary sentence rhythm. Max 1 emoji.
- If has_link is true: include the exact link once. Put this disclosure at the {disclosure_position}: "{disclosure_text}".
- If has_link is false (e.g. general tips or question): do not include any links or affiliate disclosure.

Return ONLY a valid JSON object matching this exact schema:
{{
  "variants": [
    {{
      "parts": ["Post text here..."],
      "has_link": true,
      "link_placement": "in_post",
      "angle": "Brief angle summary (e.g. space saving)",
      "hook_type": "observation"
    }}
  ]
}}
Do NOT output markdown code fences (no ```json). Output raw JSON only."""

    # Build User Prompt
    if product:
        benefits_text = product.benefits or "[]"
        try:
            benefits_list = json.loads(benefits_text)
            benefits_str = "; ".join(benefits_list) if isinstance(benefits_list, list) else str(benefits_text)
        except Exception:
            benefits_str = str(benefits_text)

        user_prompt = f"""Generate {num_variants} diverse post variants for the following product:
Niche: {niche.name} ({niche.description or ''})
Product Title: {product.title}
Key Features & Benefits (from catalog): {benefits_str}
Affiliate Link: {product.benable_url}

Ensure each variant explores a distinct angle or hook (e.g. observation, tip, problem-solving, feature highlight)."""
    else:
        # Non-affiliate content (e.g. question, general tip)
        user_prompt = f"""Generate {num_variants} organic, non-affiliate post variants for the niche:
Niche: {niche.name} ({niche.description or ''})
Style: {style.name}

These posts should spark thoughtful discussion or offer useful general advice without any links or products."""

    return system_instruction, user_prompt
