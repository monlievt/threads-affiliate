"""app/safety/validators.py — Automated content safety and compliance validator.

Enforces all 11 V-* rules from docs/06-SAFETY-COMPLIANCE.md §4:
- V-LEN: Text length <= 500 chars (or style max_chars)
- V-DISC: Clear affiliate disclosure (e.g. 'Affiliate link', '#ad')
- V-LINK: Allowlist domain only (benable.com), max 1 link, no shorteners, no cloaking
- V-PRICE: Zero price numbers, discount %, 'sale', 'lowest price', stock claims
- V-CLAIM: No health/medical claims, guaranteed results, unsubstantiated #1/best, fake personal experience
- V-URGE: No fake urgency ('only 3 left', 'ends tonight', 'hurry')
- V-SENS: No sensitive/political/adult topics
- V-ENG: No prohibited engagement bait ('like to win', 'tag a friend to enter')
- V-REPEAT: No repeating recent post openers
- V-SIM: Handled in similarity.py / integrated report
- V-MISC: Max 2 hashtags, no zero-width / hidden characters, no unsolicited @mentions
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class ValidationResult(BaseModel):
    """Result of a single rule check."""

    code: str
    valid: bool
    reason: str | None = None


class ValidatorReport(BaseModel):
    """Aggregated validation report across all rules."""

    passed: bool
    failed_codes: list[str] = Field(default_factory=list)
    results: dict[str, ValidationResult] = Field(default_factory=dict)

    @property
    def valid(self) -> bool:
        return self.passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "failed_codes": self.failed_codes,
            "results": {code: res.model_dump() for code, res in self.results.items()},
        }


# ---------------------------------------------------------------------------
# Prohibited Patterns & Wordlists
# ---------------------------------------------------------------------------
# Disallowed URL shorteners
SHORTENER_DOMAINS = frozenset([
    "bit.ly", "tinyurl.com", "amzn.to", "t.co", "goo.gl", "ow.ly", "buff.ly",
    "is.gd", "cutt.ly", "shorturl.at", "tiny.cc", "rebrand.ly",
])

# Price & discount patterns
PRICE_PATTERNS = [
    re.compile(r"[\$\£\€\¥]\s*\d+(?:[\.,]\d{2})?", re.IGNORECASE),
    re.compile(r"\b\d+\s*(?:usd|dollars|bucks|eur|gbp)\b", re.IGNORECASE),
    re.compile(r"\b\d+\s*%\s*(?:off|discount|cheaper)\b", re.IGNORECASE),
    re.compile(r"\b(?:sale|clearance|blowout|flash\s*sale|lowest\s*price|was\s*\$\d+|now\s*\$\d+)\b", re.IGNORECASE),
    re.compile(r"\b(?:in\s*stock|out\s*of\s*stock|low\s*stock)\b", re.IGNORECASE),
]

# Health / medical / miracle claims
CLAIM_PATTERNS = [
    re.compile(r"\b(?:cures?|treating|heals?|treatments?|remedy|diagnos\w+)\b", re.IGNORECASE),
    re.compile(r"\b(?:guaranteed\s*results?|100%\s*guarantee[d]?|results\s*guaranteed)\b", re.IGNORECASE),
    re.compile(r"\b(?:miracle\s*(?:cure|pill|product|solution))\b", re.IGNORECASE),
    re.compile(r"\b(?:#1\s*rated|rated\s*#1|the\s*world'?s?\s*best|unbeatable\s*quality)\b", re.IGNORECASE),
    re.compile(r"\b(?:5[\s-]*stars?\s*(?:rated|rating|by\s*me)|\u2605{3,})\b", re.IGNORECASE),  # ★★★★★ or "5-star rating by me"
]

# Fake personal use / fabricated experience patterns
FAKE_EXPERIENCE_PATTERNS = [
    re.compile(r"\b(?:i'?ve\s*been\s*using\s*this\s*for\s*\d+\s*(?:years?|months?))\b", re.IGNORECASE),
    re.compile(r"\b(?:my\s*personal\s*experience\s*after\s*\d+\s*(?:years?|months?))\b", re.IGNORECASE),
    re.compile(r"\b(?:i\s*tested\s*this\s*for\s*\d+\s*(?:years?|months?))\b", re.IGNORECASE),
    re.compile(r"\b(?:changed\s*my\s*life\s*completely)\b", re.IGNORECASE),
]

# Fake urgency patterns
URGENCY_PATTERNS = [
    re.compile(r"\b(?:only\s*\d+\s*(?:left|remaining))\b", re.IGNORECASE),
    re.compile(r"\b(?:ends?\s*(?:tonight|today|in\s*\d+\s*hours?))\b", re.IGNORECASE),
    re.compile(r"\b(?:hurry\s*before\s*it'?s?\s*(?:gone|sold\s*out))\b", re.IGNORECASE),
    re.compile(r"\b(?:act\s*now|last\s*chance|don'?t\s*wait)\b", re.IGNORECASE),
    re.compile(r"\b(?:limited\s*time\s*only|while\s*supplies\s*last)\b", re.IGNORECASE),
]

# Engagement bait
ENGAGEMENT_PATTERNS = [
    re.compile(r"\b(?:follow\s*to\s*win|like\s*to\s*win|repost\s*to\s*win)\b", re.IGNORECASE),
    re.compile(r"\b(?:giveaway\s*alert|enter\s*the\s*giveaway)\b", re.IGNORECASE),
    re.compile(r"\b(?:tag\s*(?:a\s*friend|3\s*friends)\s*to\s*win)\b", re.IGNORECASE),
    re.compile(r"\b(?:drop\s*a\s*comment\s*to\s*get\s*free)\b", re.IGNORECASE),
]

# Sensitive / political / adult topics
SENSITIVE_PATTERNS = [
    re.compile(r"\b(?:politics?|democrats?|republicans?|election\s*\d+|biden|trump)\b", re.IGNORECASE),
    re.compile(r"\b(?:porn|nsfw|xxx|escort|gambling|casino|betting)\b", re.IGNORECASE),
    re.compile(r"\b(?:toddlers?|infants?|baby|babies|kids?)\s*(?:diet|weight\s*loss|supplements?)\b", re.IGNORECASE),
]

# Zero-width / hidden characters
ZERO_WIDTH_CHARS = re.compile(r"[\u200B-\u200D\uFEFF\u00A0]")

# URL regex
URL_REGEX = re.compile(r"https?://[^\s]+", re.IGNORECASE)

# Hashtag regex
HASHTAG_REGEX = re.compile(r"#\w+", re.UNICODE)

# User mention regex
MENTION_REGEX = re.compile(r"@\w+", re.UNICODE)


# ---------------------------------------------------------------------------
# Granular Validator Functions
# ---------------------------------------------------------------------------
def validate_v_len(text: str, max_chars: int = 500) -> ValidationResult:
    """V-LEN: Text length must be <= max_chars (hard limit 500)."""
    length = len(text.strip())
    if length == 0:
        return ValidationResult(code="V-LEN", valid=False, reason="Text is empty.")
    if length > max_chars:
        return ValidationResult(
            code="V-LEN",
            valid=False,
            reason=f"Length {length} exceeds maximum {max_chars} characters.",
        )
    return ValidationResult(code="V-LEN", valid=True)


def validate_v_disc(
    text: str,
    *,
    is_affiliate: bool = True,
    disclosure_text: str = "Affiliate link",
    position: str = "end",
) -> ValidationResult:
    """V-DISC: Affiliate posts MUST contain the designated disclosure clearly visible."""
    if not is_affiliate:
        return ValidationResult(code="V-DISC", valid=True)

    target = disclosure_text.strip().lower()
    lower_text = text.lower()

    if target not in lower_text:
        return ValidationResult(
            code="V-DISC",
            valid=False,
            reason=f"Affiliate post missing required disclosure: {disclosure_text!r}.",
        )

    # Check if disclosure is hidden behind ellipsis
    if f"...{target}" in lower_text or f"…{target}" in lower_text:
        return ValidationResult(
            code="V-DISC",
            valid=False,
            reason="Disclosure appears obscured or hidden behind ellipsis.",
        )

    return ValidationResult(code="V-DISC", valid=True)


def validate_v_link(
    text: str,
    *,
    allowlist_domains: tuple[str, ...] = ("benable.com",),
) -> ValidationResult:
    """V-LINK: Maximum 1 link, domain strictly in allowlist, no shorteners or spoofing."""
    urls = URL_REGEX.findall(text)
    if len(urls) == 0:
        return ValidationResult(code="V-LINK", valid=True)

    if len(urls) > 1:
        return ValidationResult(
            code="V-LINK",
            valid=False,
            reason=f"Found {len(urls)} links; maximum 1 link per post is allowed.",
        )

    url = urls[0]
    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or "").lower()

    # Reject shorteners
    if hostname in SHORTENER_DOMAINS:
        return ValidationResult(
            code="V-LINK",
            valid=False,
            reason=f"Prohibited URL shortener domain: {hostname!r}.",
        )

    # Must be HTTPS
    if parsed.scheme != "https":
        return ValidationResult(
            code="V-LINK",
            valid=False,
            reason="Link must use secure HTTPS protocol.",
        )

    # Exact domain or subdomain of allowlist
    is_allowed = any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in allowlist_domains
    )

    if not is_allowed:
        return ValidationResult(
            code="V-LINK",
            valid=False,
            reason=f"Domain {hostname!r} is not on the affiliate allowlist ({allowlist_domains}).",
        )

    return ValidationResult(code="V-LINK", valid=True)


def validate_v_price(text: str) -> ValidationResult:
    """V-PRICE: Zero price numbers, discount percentages, 'sale', or stock claims."""
    for pattern in PRICE_PATTERNS:
        match = pattern.search(text)
        if match:
            return ValidationResult(
                code="V-PRICE",
                valid=False,
                reason=f"Prohibited price/discount/sale mention: {match.group()!r}.",
            )
    return ValidationResult(code="V-PRICE", valid=True)


def validate_v_claim(text: str) -> ValidationResult:
    """V-CLAIM: No health/medical claims, guaranteed results, or fabricated personal use."""
    for pattern in CLAIM_PATTERNS:
        match = pattern.search(text)
        if match:
            return ValidationResult(
                code="V-CLAIM",
                valid=False,
                reason=f"Prohibited medical/guaranteed claim: {match.group()!r}.",
            )

    for pattern in FAKE_EXPERIENCE_PATTERNS:
        match = pattern.search(text)
        if match:
            return ValidationResult(
                code="V-CLAIM",
                valid=False,
                reason=f"Prohibited fabricated personal experience: {match.group()!r}.",
            )

    return ValidationResult(code="V-CLAIM", valid=True)


def validate_v_urge(text: str) -> ValidationResult:
    """V-URGE: No artificial scarcity or urgency claims."""
    for pattern in URGENCY_PATTERNS:
        match = pattern.search(text)
        if match:
            return ValidationResult(
                code="V-URGE",
                valid=False,
                reason=f"Prohibited urgency phrase: {match.group()!r}.",
            )
    return ValidationResult(code="V-URGE", valid=True)


def validate_v_sens(text: str) -> ValidationResult:
    """V-SENS: No sensitive, adult, or political topics."""
    for pattern in SENSITIVE_PATTERNS:
        match = pattern.search(text)
        if match:
            return ValidationResult(
                code="V-SENS",
                valid=False,
                reason=f"Prohibited sensitive/adult/political content: {match.group()!r}.",
            )
    return ValidationResult(code="V-SENS", valid=True)


def validate_v_eng(text: str) -> ValidationResult:
    """V-ENG: No prohibited engagement baiting or unverified giveaways."""
    for pattern in ENGAGEMENT_PATTERNS:
        match = pattern.search(text)
        if match:
            return ValidationResult(
                code="V-ENG",
                valid=False,
                reason=f"Prohibited engagement bait: {match.group()!r}.",
            )
    return ValidationResult(code="V-ENG", valid=True)


def validate_v_repeat(
    text: str,
    recent_openers: list[str] | None = None,
) -> ValidationResult:
    """V-REPEAT: Disallow repeating the exact opening sentence/phrase from recent posts."""
    if not recent_openers:
        return ValidationResult(code="V-REPEAT", valid=True)

    # Extract first sentence or first 6 words as opener
    cleaned = text.strip()
    words = cleaned.split()
    current_opener = " ".join(words[:6]).lower()

    for opener in recent_openers:
        opener_clean = " ".join(opener.strip().split()[:6]).lower()
        if current_opener and current_opener == opener_clean:
            return ValidationResult(
                code="V-REPEAT",
                valid=False,
                reason=f"Opening phrase repeats recent post opener: {opener_clean!r}.",
            )

    return ValidationResult(code="V-REPEAT", valid=True)


def validate_v_misc(text: str, max_hashtags: int = 2) -> ValidationResult:
    """V-MISC: Maximum 2 hashtags, no zero-width chars, no unsolicited user @mentions."""
    # Zero-width / hidden characters
    if ZERO_WIDTH_CHARS.search(text):
        return ValidationResult(
            code="V-MISC",
            valid=False,
            reason="Prohibited zero-width or hidden unicode characters detected.",
        )

    # Hashtags limit
    hashtags = HASHTAG_REGEX.findall(text)
    if len(hashtags) > max_hashtags:
        return ValidationResult(
            code="V-MISC",
            valid=False,
            reason=f"Found {len(hashtags)} hashtags; maximum allowed is {max_hashtags}.",
        )

    # Mentions check
    mentions = MENTION_REGEX.findall(text)
    if mentions:
        return ValidationResult(
            code="V-MISC",
            valid=False,
            reason=f"Unsolicited @mentions are prohibited: {mentions!r}.",
        )

    return ValidationResult(code="V-MISC", valid=True)


# ---------------------------------------------------------------------------
# Aggregated Content Validator
# ---------------------------------------------------------------------------
def validate_content(
    text: str,
    *,
    is_affiliate: bool = True,
    disclosure_text: str = "Affiliate link",
    max_chars: int = 500,
    recent_openers: list[str] | None = None,
    allowlist_domains: tuple[str, ...] = ("benable.com",),
) -> ValidatorReport:
    """Run all content validators against a text.

    Returns:
        ValidatorReport containing pass/fail state and granular rule results.
    """
    validators = [
        validate_v_len(text, max_chars=max_chars),
        validate_v_disc(text, is_affiliate=is_affiliate, disclosure_text=disclosure_text),
        validate_v_link(text, allowlist_domains=allowlist_domains),
        validate_v_price(text),
        validate_v_claim(text),
        validate_v_urge(text),
        validate_v_sens(text),
        validate_v_eng(text),
        validate_v_repeat(text, recent_openers=recent_openers),
        validate_v_misc(text),
    ]

    results: dict[str, ValidationResult] = {}
    failed_codes: list[str] = []

    for res in validators:
        results[res.code] = res
        if not res.valid:
            failed_codes.append(res.code)

    return ValidatorReport(
        passed=len(failed_codes) == 0,
        failed_codes=failed_codes,
        results=results,
    )

