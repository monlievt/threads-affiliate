"""app/content/prompts/f10_comment.py — Prompt builder for Value-First Comments (Feature 10).

Follows strict guidelines from docs/06-SAFETY-COMPLIANCE.md §7:
- Value-first: No spammy behavior, no aggressive self-promotion
- Zero prices, discounts, or deals
- Concise: < 250 characters
- Generates 3 distinct strategic angles: insight, relate, question
"""

from __future__ import annotations

import json
from typing import Any

AVOID_LIST_COMMON = [
  "Great post! / Nice!",
  "Check my bio / link in bio",
  "DM me for more info",
  "Prices, discounts, promo codes, % off",
  "Fake personal claims or medical claims",
  "Aggressive self-promotion",
]


def build_comment_prompt(
    *,
    target_post_text: str,
    target_post_url: str,
    niche_name: str | None = None,
    persona_voice: str | None = None,
    include_link: bool = False,
    link_url: str | None = None,
    strategy: str = "all",
) -> tuple[str, str]:
    """Construct system instructions and user prompt for Feature 10 Comments."""
    system_instruction = f"""You write concise, high-value replies to Threads posts for an English-speaking audience in the United States.
Voice tone: {persona_voice or 'Humble, articulate curator and knowledgeable peer. Natural and authentic human tone.'}
Context niche: {niche_name or 'General Lifestyle / Tech / Design'}

Hard Safety & Algorithmic Rules:
1. VALUE-FIRST: Do NOT sound like a marketer, spam bot, or sales person.
2. ZERO PRICE POLICY: Never mention prices, dollars ($), discounts, % off, sales, or deals.
3. CONCISE: Keep each reply under 250 characters. Punchy, thoughtful, respectful.
4. FORBIDDEN PATTERNS:
   - No generic spam openers like "Great post!", "Nice!", "So true!", "Love this!".
   - No engagement bait ("Follow me", "Check my profile").
   - Max 1 relevant emoji (or none).
5. LINK POLICY:
   {"- INCLUDE LINK: Mention the discovery naturally with link at end: " + link_url if include_link and link_url else "- NO LINKS: Pure insight and conversation value only. Do NOT include any URLs or promotion."}

Provide exactly 3 distinct reply variations corresponding to these strategies:
- 'insight': Adds a practical tip, fresh perspective, or nuance the author didn't mention.
- 'relate': Empathetic human connection, sharing a relatable observation.
- 'question': A genuine, open-ended question that sparks an engaging discussion.

Format Output:
Return ONLY valid JSON matching this schema:
{{
  "options": [
    {{
      "strategy": "insight",
      "text": "<reply text under 250 chars>"
    }},
    {{
      "strategy": "relate",
      "text": "<reply text under 250 chars>"
    }},
    {{
      "strategy": "question",
      "text": "<reply text under 250 chars>"
    }}
  ]
}}
"""

    user_prompt = f"""Target Post being replied to:
\"\"\"{target_post_text.strip()}\"\"\"

Generate 3 high-value, authentic reply options."""

    return system_instruction, user_prompt
