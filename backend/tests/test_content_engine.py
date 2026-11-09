"""tests/test_content_engine.py — Tests for ContentEngine, p_v1 prompt template, and parser."""

from __future__ import annotations

import json
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.content.engine import ContentEngine
from app.content.llm.fake import FakeLLMProvider
from app.content.parser import parse_generation_output
from app.content.prompts.p_v1 import build_p_v1_prompt
from app.db.models import Account, Draft, Niche, Persona, Product, Style


@pytest.fixture
async def content_entities(db_session: AsyncSession) -> tuple[Account, Niche, Style, Product]:
    """Fixture returning required entities for content engine tests."""
    account = Account(username="engine_tester", threads_user_id="th_eng_1")
    db_session.add(account)
    await db_session.commit()

    persona = Persona(
        account_id=account.id,
        name="Coffee Curator",
        voice="Thoughtful coffee enthusiast",
        disclosure_text="Affiliate link",
    )
    db_session.add(persona)

    niche = Niche(name="specialty_coffee", description="Pour-over and espresso gear")
    db_session.add(niche)
    await db_session.commit()

    style = Style(
        name="curator",
        description="Curator tone",
        tone_rules="Humble, highlight 1 benefit",
        max_chars=400,
    )
    db_session.add(style)

    product = Product(
        niche_id=niche.id,
        title="Ceramic Pour-Over Dripper",
        benable_url="https://benable.com/coffee/dripper",
        benefits=json.dumps(["Dual micro-mesh filter", "Heat-resistant collar"]),
    )
    db_session.add(product)
    await db_session.commit()

    return account, niche, style, product


def test_build_p_v1_prompt() -> None:
    """Test p_v1 prompt builder outputs instructions forbidding prices and enforcing disclosure."""
    persona = Persona(account_id="acc", name="Curator", voice="Humble", disclosure_text="Affiliate link")
    style = Style(name="curator", description="Desc", tone_rules="Tone", max_chars=400)
    niche = Niche(name="kitchen")
    product = Product(niche_id="n1", title="Pot Strainer", benable_url="https://benable.com/p/1", benefits='["Compact"]')

    sys_prompt, user_prompt = build_p_v1_prompt(
        persona=persona,
        style=style,
        niche=niche,
        product=product,
        country="US",
        recent_openers=["Found this item"],
        num_variants=2,
    )

    assert "Affiliate link" in sys_prompt
    assert "Never state prices" in sys_prompt
    assert "Pot Strainer" in user_prompt
    assert "https://benable.com/p/1" in user_prompt


def test_parse_generation_output_with_markdown_fences() -> None:
    """Test parser strips markdown ```json code blocks."""
    raw = """```json
    {
      "variants": [
        {
          "parts": ["Clean post text."],
          "has_link": true,
          "link_placement": "in_post",
          "angle": "utility",
          "hook_type": "observation"
        }
      ]
    }
    ```"""
    parsed = parse_generation_output(raw)
    assert len(parsed.variants) == 1
    assert parsed.variants[0].parts == ["Clean post text."]
    assert parsed.variants[0].has_link is True


def test_parse_generation_output_invalid_json() -> None:
    """Test parser raises ValueError on broken JSON."""
    with pytest.raises(ValueError, match="is not valid JSON"):
        parse_generation_output("Not JSON")


@pytest.mark.asyncio
async def test_content_engine_generates_pending_review_draft(
    db_session: AsyncSession,
    content_entities: tuple[Account, Niche, Style, Product],
) -> None:
    """Test full generation flow when LLM output complies with all safety rules."""
    account, niche, style, product = content_entities

    compliant_json = json.dumps({
        "variants": [
            {
                "parts": [
                    "Found this ceramic pour-over dripper with dual micro-mesh filtering. Saves cabinet space and cleans easily. Find it here: https://benable.com/coffee/dripper Affiliate link"
                ],
                "has_link": True,
                "link_placement": "in_post",
                "angle": "space saving",
                "hook_type": "observation",
            }
        ]
    })

    fake_llm = FakeLLMProvider(canned_responses=[compliant_json])
    engine = ContentEngine(llm_provider=fake_llm, model_name="fake-model")

    drafts = await engine.generate_drafts(
        db_session,
        account_id=account.id,
        niche_id=niche.id,
        style_id=style.id,
        product_id=product.id,
        num_variants=1,
    )

    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.status == "pending_review"
    assert draft.reject_reason is None
    assert draft.llm_raw_response == compliant_json
    assert draft.validator_report is not None


@pytest.mark.asyncio
async def test_content_engine_marks_violations_as_rejected_auto(
    db_session: AsyncSession,
    content_entities: tuple[Account, Niche, Style, Product],
) -> None:
    """Test that a variant violating content safety rules is flagged rejected_auto."""
    account, niche, style, product = content_entities

    violating_json = json.dumps({
        "variants": [
            {
                "parts": [
                    "Massive 50% discount on this miracle cure dripper! Only $19.99 ends tonight hurry!"
                ],
                "has_link": False,
                "link_placement": "none",
                "angle": "urgency",
                "hook_type": "observation",
            }
        ]
    })

    fake_llm = FakeLLMProvider(canned_responses=[violating_json])
    engine = ContentEngine(llm_provider=fake_llm, model_name="fake-model")

    drafts = await engine.generate_drafts(
        db_session,
        account_id=account.id,
        niche_id=niche.id,
        style_id=style.id,
        product_id=product.id,
        num_variants=1,
    )

    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.status == "rejected_auto"
    assert draft.reject_reason is not None
    assert "Violated content rules" in draft.reject_reason
    assert draft.validator_report is not None
    assert "V-PRICE" in draft.validator_report
