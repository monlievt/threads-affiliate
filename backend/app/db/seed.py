"""app/db/seed.py — Initial seed data for content styles and default system state.

Seeds the 5 initial content styles defined in docs/07-CONTENT-EXPERIMENT.md §4.4:
  1. curator
  2. quick_review
  3. tips
  4. pros_cons
  5. question

Also ensures default system_state exists (kill_switch = 'on').
"""

from __future__ import annotations

import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Style, SystemState

INITIAL_STYLES: list[dict] = [
    {
        "name": "curator",
        "description": "Curated find style — humble, clear singular benefit, genuine discovery tone without claiming personal ownership.",
        "tone_rules": "Humble curator voice. Highlight 1 specific, practical everyday benefit. Frame as 'Found this, looks handy for X'. No exaggerated praise, no fake personal use claims.",
        "max_chars": 400,
        "good_examples": json.dumps([
            "Found this compact silicone strainer that clips right onto standard pots. Saves cabinet space and makes pasta nights slightly less messy. Affiliate link in bio.",
            "If you work at a small desk, this under-desk cable tray caught my eye. Simple clamp mount, no drilling into wood. Affiliate link below."
        ]),
        "bad_examples": json.dumps([
            "OMG this is the BEST product ever buy now 50% off!!",
            "I've been using this everyday for 3 years and it cured my back pain."
        ]),
        "status": "active",
    },
    {
        "name": "quick_review",
        "description": "Feature breakdown style — 2-3 key specs or design features summarized objectively from catalog data.",
        "tone_rules": "Objective feature summary. Group 2-3 key features, explain who it is best suited for. Never claim hands-on testing unless documented.",
        "max_chars": 400,
        "good_examples": json.dumps([
            "Quick breakdown of this magnetic phone stand:\n• Weighted zinc base (doesn't tip)\n• 360-degree ball joint\n• Fits MagSafe cases\nGood option if you take lots of desk video calls. Affiliate link below.",
            "Stainless steel pour-over dripper:\n• Dual-layer micro mesh (no paper filters needed)\n• Heat-resistant silicone grip\n• Fits mugs up to 4 inches wide\nUseful for minimalist coffee setups. Link in comments."
        ]),
        "bad_examples": json.dumps([
            "Rated 5 stars by me! Best quality guaranteed!",
            "Blowout sale ends midnight, limited stock remaining!"
        ]),
        "status": "active",
    },
    {
        "name": "tips",
        "description": "Practical niche tip style — helpful lifestyle or utility advice with the product featured neutrally as an enabler.",
        "tone_rules": "Value-first practical tip. The advice must stand on its own even if the reader never buys the product. The product is introduced gently as a tool that simplifies the tip.",
        "max_chars": 400,
        "good_examples": json.dumps([
            "A simple trick to keep cast iron pans lasting: dry them completely on a low burner for 2 minutes before storing, not just towel-drying.\nIf you don't have a chainmail scrubber yet, this small one makes cleaning without soap much easier. Affiliate link below.",
            "When organizing a tight pantry, use vertical tiered risers so canned goods don't get lost in the back. Here's a bamboo 3-tier expander that fits most shelf depths. Link in thread."
        ]),
        "bad_examples": json.dumps([
            "Tip: Buy this now to save money instantly!",
            "Secret hack the pros don't want you to know (click link)!"
        ]),
        "status": "active",
    },
    {
        "name": "pros_cons",
        "description": "Balanced evaluation style — honest trade-offs including common limitations of the category to build trust.",
        "tone_rules": "Honest trade-offs. Must include at least 1 genuine limitation or who it is NOT for. Builds long-term credibility by avoiding one-sided hype.",
        "max_chars": 400,
        "good_examples": json.dumps([
            "Ceramic non-stick frying pans — quick reality check:\nPros: super slick cooking, lightweight, completely PTFE/PFOA free.\nCons: shouldn't be used with high heat, hand-wash only if you want the coating to last.\nThis 10-inch skillet is solid if you stick to medium-low heat cooking. Affiliate link below.",
            "Mechanical keyboards with silent switches:\nPros: great tactile feel, won't annoy coworkers on calls.\nCons: keycaps sit slightly taller than membrane boards, takes 2-3 days to get used to.\nSolid starter option linked below."
        ]),
        "bad_examples": json.dumps([
            "There are zero cons, this item is 100% flawless!",
            "Don't buy anything else, this completely destroys the competition."
        ]),
        "status": "active",
    },
    {
        "name": "question",
        "description": "Community discussion style (non-affiliate) — genuine question or debate topic to foster organic community engagement.",
        "tone_rules": "Discussion-starter without sales intent. Zero links, zero promotion. Focus on relatable choices, habits, or debates in the niche.",
        "max_chars": 300,
        "good_examples": json.dumps([
            "For anyone working remotely: do you prefer a dedicated monitor riser with storage underneath, or an adjustable monitor arm that clamps to the back edge?",
            "Serious coffee drinkers: do you weigh your beans every morning or do you eyeball by the scoop once you know your routine?"
        ]),
        "bad_examples": json.dumps([
            "Who wants this free gadget? Like and retweet!",
            "Do you want to buy my recommended product? Link in bio!"
        ]),
        "status": "active",
    },
]


async def seed_initial_styles(session: AsyncSession) -> int:
    """Seed the 5 default content styles if they do not exist.

    Returns:
        Number of newly inserted styles.
    """
    inserted = 0
    for style_data in INITIAL_STYLES:
        existing = await session.scalar(
            select(Style).where(Style.name == style_data["name"])
        )
        if not existing:
            style = Style(**style_data)
            session.add(style)
            inserted += 1

    # Also seed initial system_state for kill switch
    kill_switch_state = await session.scalar(
        select(SystemState).where(SystemState.key == "kill_switch")
    )
    if not kill_switch_state:
        session.add(SystemState(key="kill_switch", value="on"))
        session.add(SystemState(key="kill_reason", value="Default ON at startup"))

    await session.commit()
    return inserted
