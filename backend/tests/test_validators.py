"""tests/test_validators.py — Comprehensive test suite for all 11 content validator rules."""

from __future__ import annotations

import pytest

from app.safety.validators import (
    validate_content,
    validate_v_claim,
    validate_v_disc,
    validate_v_eng,
    validate_v_len,
    validate_v_link,
    validate_v_misc,
    validate_v_price,
    validate_v_repeat,
    validate_v_sens,
    validate_v_urge,
)


# ---------------------------------------------------------------------------
# 1. V-LEN Tests (Text length)
# ---------------------------------------------------------------------------
def test_v_len_valid_cases() -> None:
    """5 positive cases for text length."""
    assert validate_v_len("Short text.").valid is True
    assert validate_v_len("A" * 150).valid is True
    assert validate_v_len("A" * 350).valid is True
    assert validate_v_len("A" * 499).valid is True
    assert validate_v_len("A" * 500).valid is True


def test_v_len_invalid_cases() -> None:
    """5 negative cases for text length."""
    assert validate_v_len("").valid is False  # Empty
    assert validate_v_len("    ").valid is False  # Whitespace only
    assert validate_v_len("A" * 501).valid is False  # Exceeds 500
    assert validate_v_len("A" * 650).valid is False  # Far exceeds 500
    assert validate_v_len("A" * 301, max_chars=300).valid is False  # Custom max_chars


# ---------------------------------------------------------------------------
# 2. V-DISC Tests (Affiliate disclosure)
# ---------------------------------------------------------------------------
def test_v_disc_valid_cases() -> None:
    """5 positive cases for disclosure."""
    assert validate_v_disc("Check out this pan. Affiliate link in bio.").valid is True
    assert validate_v_disc("Desk setup accessory. Affiliate link below.").valid is True
    assert validate_v_disc("Great pour-over cone. #ad linked below.", disclosure_text="#ad").valid is True
    assert validate_v_disc("Clean coffee tips. No products mentioned.", is_affiliate=False).valid is True
    assert validate_v_disc("Curated find for small kitchens (Affiliate link).").valid is True


def test_v_disc_invalid_cases() -> None:
    """5 negative cases for disclosure."""
    # Missing completely
    assert validate_v_disc("Great product buy it here!").valid is False
    # Hidden behind ellipsis
    assert validate_v_disc("Check this item...Affiliate link").valid is False
    assert validate_v_disc("Check this item…affiliate link").valid is False
    # Misspelled disclosure
    assert validate_v_disc("Awesome stand. Affliate link below.").valid is False
    # Empty disclosure text configured
    assert validate_v_disc("No disclosure here", disclosure_text="").valid is False


# ---------------------------------------------------------------------------
# 3. V-LINK Tests (Domain allowlist, shorteners, no cloaking)
# ---------------------------------------------------------------------------
def test_v_link_valid_cases() -> None:
    """5 positive cases for links."""
    assert validate_v_link("No link in this post at all.").valid is True
    assert validate_v_link("Find it here: https://benable.com/curator/great-pans").valid is True
    assert validate_v_link("Organized list: https://app.benable.com/list/123").valid is True
    assert validate_v_link("Check: https://benable.com/p/silicone-clip").valid is True
    assert validate_v_link("Custom allowlist: https://partner.example.com/p/1", allowlist_domains=("partner.example.com",)).valid is True


def test_v_link_invalid_cases() -> None:
    """5 negative cases for links."""
    # Non-allowlist domain
    assert validate_v_link("https://amazon.com/dp/B08XYZ").valid is False
    # URL Shorteners
    assert validate_v_link("https://bit.ly/3test123").valid is False
    assert validate_v_link("https://amzn.to/shorturl").valid is False
    assert validate_v_link("https://tinyurl.com/kitchengadget").valid is False
    # Domain spoofing / typo-squatting
    assert validate_v_link("https://benable.com.evil.io/phish").valid is False
    # Insecure HTTP
    assert validate_v_link("http://benable.com/item").valid is False
    # Multiple links
    assert validate_v_link("https://benable.com/a and https://benable.com/b").valid is False


# ---------------------------------------------------------------------------
# 4. V-PRICE Tests (Zero prices, discounts, sales, stock claims)
# ---------------------------------------------------------------------------
def test_v_price_valid_cases() -> None:
    """5 positive cases without price mentions."""
    assert validate_v_price("A great addition to any minimalist home office.").valid is True
    assert validate_v_price("Solid build quality with brushed aluminum finish.").valid is True
    assert validate_v_price("Saves counter space and cleans easily under warm water.").valid is True
    assert validate_v_price("Pair this with a wooden chopping board for best results.").valid is True
    assert validate_v_price("Designed specifically for pour-over coffee routines.").valid is True


def test_v_price_invalid_cases() -> None:
    """5 negative cases containing price or discount mentions."""
    assert validate_v_price("Grab this for only $19.99 right now!").valid is False
    assert validate_v_price("Costs about 25 bucks on Amazon.").valid is False
    assert validate_v_price("Currently 30% off for the summer!").valid is False
    assert validate_v_price("Massive clearance blowout sale!").valid is False
    assert validate_v_price("Low stock remaining, grab yours today.").valid is False


# ---------------------------------------------------------------------------
# 5. V-CLAIM Tests (No health claims, guaranteed results, fake personal use)
# ---------------------------------------------------------------------------
def test_v_claim_valid_cases() -> None:
    """5 positive cases with honest, humble curation tone."""
    assert validate_v_claim("Found this clamp-on headphone holder that frees up desk clutter.").valid is True
    assert validate_v_claim("Dual micro-mesh filter means you don't need disposable paper filters.").valid is True
    assert validate_v_claim("Note that cast iron takes longer to heat up than stainless steel.").valid is True
    assert validate_v_claim("Useful option if you spend lots of time on video calls.").valid is True
    assert validate_v_claim("A compact cable organizer that sticks to the underside of tables.").valid is True


def test_v_claim_invalid_cases() -> None:
    """5 negative cases containing exaggerated claims or fake experience."""
    assert validate_v_claim("This magic tea cures all joint pain permanently!").valid is False
    assert validate_v_claim("100% guaranteed results in 7 days or your money back!").valid is False
    assert validate_v_claim("I've been using this for 3 years every single morning.").valid is False
    assert validate_v_claim("The world's best frying pan that destroys all competitors!").valid is False
    assert validate_v_claim("Rated 5 stars by me! ★★★★★ unbeatable quality!").valid is False


# ---------------------------------------------------------------------------
# 6. V-URGE Tests (Fake urgency & scarcity)
# ---------------------------------------------------------------------------
def test_v_urge_valid_cases() -> None:
    """5 positive cases without fake urgency."""
    assert validate_v_urge("A handy everyday tool for meal prepping on weekends.").valid is True
    assert validate_v_urge("Take your time choosing the right grind size for aeropress.").valid is True
    assert validate_v_urge("Works well for students in compact dorm rooms.").valid is True
    assert validate_v_urge("Simple magnetic closure keeps cables from slipping.").valid is True
    assert validate_v_urge("Worth looking into if you want an organized nightstand.").valid is True


def test_v_urge_invalid_cases() -> None:
    """5 negative cases with artificial urgency."""
    assert validate_v_urge("Hurry before it's gone forever!").valid is False
    assert validate_v_urge("Only 3 left in inventory!").valid is False
    assert validate_v_urge("This special deal ends tonight at midnight!").valid is False
    assert validate_v_urge("Act now, don't wait another minute!").valid is False
    assert validate_v_urge("Last chance to grab this item!").valid is False


# ---------------------------------------------------------------------------
# 7. V-SENS Tests (Sensitive, political, adult content)
# ---------------------------------------------------------------------------
def test_v_sens_valid_cases() -> None:
    """5 positive cases on safe lifestyle/utility niches."""
    assert validate_v_sens("Organizing your spices in glass jars makes cooking faster.").valid is True
    assert validate_v_sens("A heavy brass pen with smooth rollerball ink.").valid is True
    assert validate_v_sens("Cat scratching post with natural sisal rope.").valid is True
    assert validate_v_sens("Portable campfire kettle made from hard-anodized aluminum.").valid is True
    assert validate_v_sens("Ergonomic wrist rest with cooling memory foam.").valid is True


def test_v_sens_invalid_cases() -> None:
    """5 negative cases with sensitive or inappropriate topics."""
    assert validate_v_sens("Election 2026 political debate commentary").valid is False
    assert validate_v_sens("Online casino gambling and betting tips").valid is False
    assert validate_v_sens("Explicit adult xxx webcam service").valid is False
    assert validate_v_sens("Toddler weight loss diet supplement program").valid is False
    assert validate_v_sens("Controversial partisan politics manifesto").valid is False


# ---------------------------------------------------------------------------
# 8. V-ENG Tests (Prohibited engagement bait)
# ---------------------------------------------------------------------------
def test_v_eng_valid_cases() -> None:
    """5 positive cases with organic conversation."""
    assert validate_v_eng("What's your favorite go-to kitchen gadget?").valid is True
    assert validate_v_eng("Found this thoughtful gift idea for coffee lovers.").valid is True
    assert validate_v_eng("Do you prefer wireless mechanical keyboards or slim laptop keys?").valid is True
    assert validate_v_eng("Here's a breakdown of the pros and cons of ceramic cookware.").valid is True
    assert validate_v_eng("Hope this helps anyone planning a small home workspace.").valid is True


def test_v_eng_invalid_cases() -> None:
    """5 negative cases containing engagement bait."""
    assert validate_v_eng("Follow to win a free MacBook! Like and repost!").valid is False
    assert validate_v_eng("Giveaway alert! Drop a comment to enter!").valid is False
    assert validate_v_eng("Tag 3 friends to win our biggest prize!").valid is False
    assert validate_v_eng("Drop a comment to get free instant cash!").valid is False
    assert validate_v_eng("Like to win today!").valid is False


# ---------------------------------------------------------------------------
# 9. V-REPEAT Tests (Repetitive openers)
# ---------------------------------------------------------------------------
def test_v_repeat_cases() -> None:
    """Test opener repetition checks."""
    recent_openers = [
        "If you work at a desk",
        "Found this compact silicone strainer yesterday",
        "Here is a quick breakdown of",
    ]

    # Fresh opener -> passes
    assert validate_v_repeat("A simple trick for keeping pans clean", recent_openers).valid is True
    assert validate_v_repeat("For anyone who loves black coffee", recent_openers).valid is True

    # Repeated opener -> fails
    assert validate_v_repeat("If you work at a desk every single day", recent_openers).valid is False
    assert validate_v_repeat("Found this compact silicone strainer yesterday on sale", recent_openers).valid is False


# ---------------------------------------------------------------------------
# 10. V-MISC Tests (Hashtag limits, zero-width chars, @mentions)
# ---------------------------------------------------------------------------
def test_v_misc_valid_cases() -> None:
    """5 positive cases for formatting rules."""
    assert validate_v_misc("Clean post text without any tags.").valid is True
    assert validate_v_misc("Post with one hashtag #desksetup").valid is True
    assert validate_v_misc("Post with two hashtags #desksetup #wfh").valid is True
    assert validate_v_misc("Coffee lover morning routine #coffee #morning").valid is True
    assert validate_v_misc("Simple clean tips.").valid is True


def test_v_misc_invalid_cases() -> None:
    """5 negative cases violating formatting rules."""
    # 3 hashtags (exceeds max 2)
    assert validate_v_misc("Great setup #home #desk #workspace").valid is False
    assert validate_v_misc("#a #b #c #d spam hashtags").valid is False
    # Unsolicited user mention
    assert validate_v_misc("Hey @random_user check this out!").valid is False
    # Zero-width hidden characters
    assert validate_v_misc("Secret\u200Bhidden text").valid is False
    assert validate_v_misc("BOM\uFEFFmarker hidden").valid is False


# ---------------------------------------------------------------------------
# 11. Aggregated Content Validator Tests
# ---------------------------------------------------------------------------
def test_validate_content_fully_compliant() -> None:
    """Test a fully compliant post passes all validator checks."""
    text = (
        "Found this silicone pot strainer that clips directly onto standard pans. "
        "Saves kitchen cabinet space and makes draining pasta effortless. "
        "Find it here: https://benable.com/curator/strainer-clip "
        "Affiliate link #kitchen #home"
    )
    report = validate_content(text, is_affiliate=True, disclosure_text="Affiliate link")
    assert report.passed is True
    assert len(report.failed_codes) == 0


def test_validate_content_multiple_violations() -> None:
    """Test a post failing multiple checks accurately records all failed codes."""
    dirty_text = (
        "Massive 50% off blowout sale on this miracle cure! "
        "Only 3 left in stock hurry! "
        "https://bit.ly/cheap-pills @someone #tag1 #tag2 #tag3"
    )
    report = validate_content(dirty_text, is_affiliate=True)
    assert report.passed is False
    assert "V-PRICE" in report.failed_codes
    assert "V-CLAIM" in report.failed_codes
    assert "V-URGE" in report.failed_codes
    assert "V-LINK" in report.failed_codes
    assert "V-MISC" in report.failed_codes
    assert "V-DISC" in report.failed_codes
