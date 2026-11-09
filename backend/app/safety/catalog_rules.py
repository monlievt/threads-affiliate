"""app/safety/catalog_rules.py — Safety rules for catalog products and CSV imports.

Enforces:
1. URL Allowlist (benable.com HTTPS only, no shorteners)
2. Zero Price Policy (V-PRICE: no prices, discounts, sales, deals in title, benefits, tags)
3. Prohibited column detection for CSV imports
"""

from __future__ import annotations

import re
import urllib.parse
from app.safety.validators import SHORTENER_DOMAINS, validate_v_price

DEFAULT_ALLOWLIST_DOMAINS: tuple[str, ...] = ("benable.com",)

PROHIBITED_CSV_HEADERS: frozenset[str] = frozenset({
    "price",
    "prices",
    "cost",
    "discount",
    "sale",
    "pricing",
    "was_now",
    "current_price",
    "original_price",
})


def validate_product_benable_url(
    url: str,
    allowlist_domains: tuple[str, ...] = DEFAULT_ALLOWLIST_DOMAINS,
) -> tuple[bool, str | None]:
    """Validate that product URL strictly adheres to Benable allowlist.

    - Must be valid HTTPS URL.
    - Hostname must be in allowlist (or subdomain thereof).
    - Hostname must not be a URL shortener.
    """
    if not url or not url.strip():
        return False, "URL is required and cannot be empty."

    url = url.strip()
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False, f"Malformed URL: {url!r}."

    if parsed.scheme != "https":
        return False, f"URL must use secure HTTPS protocol: {url!r}."

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False, f"Could not determine hostname in URL: {url!r}."

    if hostname in SHORTENER_DOMAINS:
        return False, f"Prohibited URL shortener domain: {hostname!r}."

    is_allowed = any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in allowlist_domains
    )
    if not is_allowed:
        return False, f"Domain {hostname!r} is not on the affiliate allowlist ({allowlist_domains})."

    return True, None


def validate_product_text_safety(
    title: str,
    benefits: list[str] | None = None,
    tags: list[str] | None = None,
) -> tuple[bool, str | None]:
    """Validate that title, benefits, and tags contain no pricing claims (V-PRICE)."""
    # 1. Title check
    v_title = validate_v_price(title)
    if not v_title.valid:
        return False, f"Title contains prohibited pricing/sale terms: {v_title.reason}"

    # 2. Benefits check
    if benefits:
        for idx, benefit in enumerate(benefits, start=1):
            v_ben = validate_v_price(benefit)
            if not v_ben.valid:
                return False, f"Benefit #{idx} contains prohibited pricing/sale terms: {v_ben.reason}"

    # 3. Tags check
    if tags:
        for idx, tag in enumerate(tags, start=1):
            v_tag = validate_v_price(tag)
            if not v_tag.valid:
                return False, f"Tag #{idx} contains prohibited pricing/sale terms: {v_tag.reason}"

    return True, None
