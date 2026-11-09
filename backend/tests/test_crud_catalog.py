"""tests/test_crud_catalog.py — Test suite for Catalog CRUD and CSV import (T-016).

Verifies:
1. URL allowlist validation (benable.com strictly enforced, shorteners rejected)
2. Zero price policy enforcement on title, benefits, tags
3. Prohibited price header rejection in CSV imports
4. Row-by-row error reporting for CSV bulk imports
5. No hard delete: soft deletion to 'archived' for niches, products, and styles
6. Persona disclosure validation (V-DISC)
7. Audit log generation for all mutations
"""

from __future__ import annotations

import json
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.audit import get_recent_audit_logs
from app.core.security import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, create_session_token
from app.db.models import Account, Niche, Persona, Product, Style
from app.safety.catalog_rules import (
    validate_product_benable_url,
    validate_product_text_safety,
)
from app.schemas.catalog import ProductImportResponse


# ---------------------------------------------------------------------------
# Unit tests: URL Allowlist & Zero Price Policy
# ---------------------------------------------------------------------------
def test_benable_url_allowlist() -> None:
    # Valid Benable URLs
    ok, err = validate_product_benable_url("https://benable.com/curator/small-kitchen-finds")
    assert ok is True
    assert err is None

    ok, err = validate_product_benable_url("https://www.benable.com/list/12345")
    assert ok is True
    assert err is None

    # Insecure HTTP
    ok, err = validate_product_benable_url("http://benable.com/list/12345")
    assert ok is False
    assert "HTTPS" in (err or "")

    # URL Shorteners
    ok, err = validate_product_benable_url("https://bit.ly/clip-strainer")
    assert ok is False
    assert "shortener" in (err or "").lower()

    # Foreign / untrusted domains
    ok, err = validate_product_benable_url("https://amazon.com/dp/B08XYZ")
    assert ok is False
    assert "allowlist" in (err or "").lower()

    # Empty
    ok, err = validate_product_benable_url("")
    assert ok is False


def test_zero_price_policy_validator() -> None:
    # Clean text
    ok, err = validate_product_text_safety(
        title="Silicone Snap N Strain Pot Colander",
        benefits=["Fits nearly all round pots and pans", "Compact space saver"],
        tags=["kitchen", "cooking"],
    )
    assert ok is True
    assert err is None

    # Price in title
    ok, err = validate_product_text_safety(
        title="Strainer for only $14.99",
        benefits=["Durable"],
    )
    assert ok is False
    assert "Title contains prohibited pricing" in (err or "")

    # Discount in benefits
    ok, err = validate_product_text_safety(
        title="Compact Silicone Strainer",
        benefits=["Get 50% off during holiday sale!"],
    )
    assert ok is False
    assert "Benefit #1 contains prohibited pricing" in (err or "")

    # Sale in tags
    ok, err = validate_product_text_safety(
        title="Compact Silicone Strainer",
        tags=["flash-sale", "gadgets"],
    )
    assert ok is False
    assert "Tag #1 contains prohibited pricing" in (err or "")


# ---------------------------------------------------------------------------
# Helper: Setup admin authenticated headers/cookies
# ---------------------------------------------------------------------------
def _get_auth_headers_and_cookies() -> tuple[dict[str, str], dict[str, str]]:
    token, csrf_token = create_session_token("admin")
    headers = {"X-CSRF-Token": csrf_token}
    cookies = {
        SESSION_COOKIE_NAME: token,
        CSRF_COOKIE_NAME: csrf_token,
    }
    return headers, cookies


# ---------------------------------------------------------------------------
# API Integration Tests: Niches CRUD & Soft Delete
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_niche_crud_and_soft_delete(client: AsyncClient, db_session: AsyncSession) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    # 1. Create Niche
    create_resp = await client.post(
        "/api/niches",
        json={
            "name": "Kitchen Organization",
            "description": "Smart small kitchen gadgets and storage hacks",
            "keywords": ["kitchen", "pantry", "storage"],
        },
        headers=headers,
        cookies=cookies,
    )
    assert create_resp.status_code == 201
    niche_data = create_resp.json()
    assert niche_data["name"] == "Kitchen Organization"
    assert niche_data["status"] == "active"
    niche_id = niche_data["id"]

    # 2. Duplicate Niche Name
    dup_resp = await client.post(
        "/api/niches",
        json={"name": "Kitchen Organization"},
        headers=headers,
        cookies=cookies,
    )
    assert dup_resp.status_code == 409

    # 3. Get Niche
    get_resp = await client.get(f"/api/niches/{niche_id}", cookies=cookies)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == niche_id

    # 4. Update Niche
    upd_resp = await client.put(
        f"/api/niches/{niche_id}",
        json={"description": "Updated pantry & kitchen hacks"},
        headers=headers,
        cookies=cookies,
    )
    assert upd_resp.status_code == 200
    assert upd_resp.json()["description"] == "Updated pantry & kitchen hacks"

    # 5. Soft-delete Niche (DELETE must set status='archived', never delete row)
    del_resp = await client.delete(f"/api/niches/{niche_id}", headers=headers, cookies=cookies)
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "archived"

    # Verify niche still exists in DB as archived
    db_niche = await db_session.get(Niche, niche_id)
    assert db_niche is not None
    assert db_niche.status == "archived"

    # List default excludes archived
    list_active = await client.get("/api/niches", cookies=cookies)
    assert not any(n["id"] == niche_id for n in list_active.json())

    # List with include_archived=True includes it
    list_all = await client.get("/api/niches?include_archived=true", cookies=cookies)
    assert any(n["id"] == niche_id for n in list_all.json())


# ---------------------------------------------------------------------------
# API Integration Tests: Products CRUD & Safety Rules
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_product_crud_and_safety_checks(client: AsyncClient, db_session: AsyncSession) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    # Create active niche
    niche = Niche(name="Home Tech", description="Smart home tech", status="active")
    db_session.add(niche)
    await db_session.commit()
    await db_session.refresh(niche)

    # 1. Invalid Allowlist URL (Reject)
    bad_url_resp = await client.post(
        "/api/products",
        json={
            "niche_id": niche.id,
            "title": "Smart LED Light Bulb",
            "benable_url": "https://unauthorized-store.com/led",
        },
        headers=headers,
        cookies=cookies,
    )
    assert bad_url_resp.status_code == 422
    assert "allowlist" in bad_url_resp.json()["detail"].lower()

    # 2. Price Claim in Title (Reject V-PRICE)
    price_title_resp = await client.post(
        "/api/products",
        json={
            "niche_id": niche.id,
            "title": "Smart LED Light Bulb only $9.99 sale",
            "benable_url": "https://benable.com/hometech/led",
        },
        headers=headers,
        cookies=cookies,
    )
    assert price_title_resp.status_code == 422
    assert "pricing" in price_title_resp.json()["detail"].lower()

    # 3. Valid Product Creation
    create_resp = await client.post(
        "/api/products",
        json={
            "niche_id": niche.id,
            "title": "Matter Compatible Smart LED Light Bulb",
            "benable_url": "https://benable.com/hometech/smart-bulb",
            "amazon_ref_url": "https://amazon.com/dp/B08LEDBULB",
            "benefits": ["Works with Apple Home and Google", "No hub required"],
            "tags": ["lighting", "home-automation"],
        },
        headers=headers,
        cookies=cookies,
    )
    assert create_resp.status_code == 201
    prod_data = create_resp.json()
    assert prod_data["title"] == "Matter Compatible Smart LED Light Bulb"
    assert prod_data["status"] == "active"
    prod_id = prod_data["id"]

    # 4. Soft-delete Product
    del_resp = await client.delete(f"/api/products/{prod_id}", headers=headers, cookies=cookies)
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "archived"

    # Verify product still exists in DB
    db_prod = await db_session.get(Product, prod_id)
    assert db_prod is not None
    assert db_prod.status == "archived"


# ---------------------------------------------------------------------------
# API Integration Tests: CSV Import & Row-by-Row Reporting
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_csv_import_prohibited_price_column(client: AsyncClient, db_session: AsyncSession) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    csv_with_price_col = (
        "title,niche,benable_url,price\n"
        "Silicone Strainer,Kitchen,https://benable.com/p/1,19.99\n"
    )

    resp = await client.post(
        "/api/products/import-csv",
        json={"csv_content": csv_with_price_col},
        headers=headers,
        cookies=cookies,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported_count"] == 0
    assert data["failed_count"] == 0  # Header validation stops before rows
    assert len(data["errors"]) > 0
    assert "Prohibited pricing column" in data["errors"][0]["reason"]


@pytest.mark.asyncio
async def test_csv_import_row_by_row_validation(client: AsyncClient, db_session: AsyncSession) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    # Pre-populate active niche
    niche = Niche(name="Coffee", description="Espresso and manual brew", status="active")
    db_session.add(niche)
    await db_session.commit()

    csv_rows = (
        "title,niche,benable_url,benefits,tags\n"
        "Manual Burr Hand Grinder,Coffee,https://benable.com/coffee/grinder,Uniform grind size;Stainless burrs,coffee;espresso\n"
        "Electric Frother for $12 Sale,Coffee,https://benable.com/coffee/frother,Easy cleanup,frother\n"
        "Silicone Tamp Mat,Unknown Niche,https://benable.com/coffee/mat,Protects counter,accessories\n"
        "Precision Scale,Coffee,https://amazon.com/scale,0.1g accuracy,scale\n"
        "Gooseneck Pour-Over Kettle,Coffee,https://benable.com/coffee/kettle,Precise flow control,pourover\n"
    )

    resp = await client.post(
        "/api/products/import-csv",
        json={"csv_content": csv_rows},
        headers=headers,
        cookies=cookies,
    )
    assert resp.status_code == 200
    res = resp.json()

    assert res["total_rows"] == 5
    assert res["imported_count"] == 2  # Grinder and Kettle
    assert res["failed_count"] == 3    # Row 2 (price in title), Row 3 (unknown niche), Row 4 (non-benable url)

    # Check error rows
    error_reasons = {err["row"]: err["reason"] for err in res["errors"]}
    assert 2 in error_reasons and "pricing" in error_reasons[2].lower()
    assert 3 in error_reasons and "not found" in error_reasons[3].lower()
    assert 4 in error_reasons and "allowlist" in error_reasons[4].lower()

    # Verify imported items in DB
    imported_titles = [p["title"] for p in res["imported_products"]]
    assert "Manual Burr Hand Grinder" in imported_titles
    assert "Gooseneck Pour-Over Kettle" in imported_titles


# ---------------------------------------------------------------------------
# API Integration Tests: Styles & Personas CRUD
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_styles_and_personas_crud(client: AsyncClient, db_session: AsyncSession) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    # 1. Styles CRUD
    style_resp = await client.post(
        "/api/styles",
        json={
            "name": "comparison_test",
            "description": "Side by side comparison breakdown",
            "tone_rules": "Objective, analytical, friendly, highlighting tradeoffs",
            "max_chars": 380,
            "good_examples": ["A is better for small spaces, B has more capacity."],
        },
        headers=headers,
        cookies=cookies,
    )
    assert style_resp.status_code == 201
    style_id = style_resp.json()["id"]

    # Soft delete style
    style_del = await client.delete(f"/api/styles/{style_id}", headers=headers, cookies=cookies)
    assert style_del.status_code == 200
    assert style_del.json()["status"] == "archived"

    # 2. Persona CRUD
    account = Account(username="tech_affiliate", automation_mode="manual_approve")
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    persona_resp = await client.post(
        "/api/personas",
        json={
            "account_id": account.id,
            "name": "Gadget Enthusiast",
            "voice": "Casual and helpful tech reviewer",
            "avoid": "Over-hyped claims and clickbait phrases",
            "disclosure_text": "Affiliate link (supports the page!)",
            "disclosure_position": "end",
        },
        headers=headers,
        cookies=cookies,
    )
    assert persona_resp.status_code == 201
    persona_id = persona_resp.json()["id"]

    # Persona with invalid disclosure (empty string) rejected
    bad_persona = await client.post(
        "/api/personas",
        json={
            "account_id": account.id,
            "name": "Bad Persona",
            "voice": "Test voice",
            "disclosure_text": "   ",
            "disclosure_position": "end",
        },
        headers=headers,
        cookies=cookies,
    )
    assert bad_persona.status_code == 422


# ---------------------------------------------------------------------------
# Audit Trail Verification
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_catalog_actions_recorded_in_audit_log(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    # Perform action: create niche
    niche_resp = await client.post(
        "/api/niches",
        json={"name": "Audit Tracked Niche"},
        headers=headers,
        cookies=cookies,
    )
    assert niche_resp.status_code == 201
    niche_id = niche_resp.json()["id"]

    # Verify audit log has the record
    logs = await get_recent_audit_logs(db_session, limit=10, action="create")
    niche_logs = [l for l in logs if l.entity == "niches" and l.entity_id == niche_id]
    assert len(niche_logs) == 1
    assert niche_logs[0].actor == "admin"
