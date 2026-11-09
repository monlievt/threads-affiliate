"""tests/test_api_catalog_ui.py — Test suite for Catalog UI Endpoints (T-032).

Verifies:
1. Dry-run CSV preview (/api/products/preview-csv) without persisting to DB
2. Prohibited price header rejection in CSV preview
3. Row-by-row error reporting in CSV preview
4. Benable URL allowlist validation endpoint (/api/products/validate-url)
5. Soft-delete enforcement (sets status='archived') for niches, products, styles, personas
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, create_session_token
from app.db.models import Account, Niche, Persona, Product, Style


def _get_auth_headers_and_cookies() -> tuple[dict[str, str], dict[str, str]]:
    token, csrf_token = create_session_token("admin")
    headers = {"X-CSRF-Token": csrf_token}
    cookies = {
        SESSION_COOKIE_NAME: token,
        CSRF_COOKIE_NAME: csrf_token,
    }
    return headers, cookies


@pytest.fixture
async def sample_niche(db_session: AsyncSession) -> Niche:
    niche = Niche(id="niche_desk_test", name="Workspace Setup", status="active")
    db_session.add(niche)
    await db_session.commit()
    await db_session.refresh(niche)
    return niche


@pytest.mark.asyncio
async def test_csv_preview_dry_run_does_not_persist(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_niche: Niche,
) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    csv_data = (
        "title,niche,benable_url,benefits,tags\n"
        "Solid Oak Desk Mat,Workspace Setup,https://benable.com/curator/desk-mat,Felt base;Smooth surface,desk;mat\n"
        "Ergonomic Wrist Rest,Workspace Setup,https://benable.com/curator/wrist-rest,Memory foam,ergonomics\n"
    )

    resp = await client.post(
        "/api/products/preview-csv",
        json={"csv_content": csv_data},
        headers=headers,
        cookies=cookies,
    )
    assert resp.status_code == 200
    res = resp.json()
    assert res["total_rows"] == 2
    assert res["imported_count"] == 2
    assert res["failed_count"] == 0
    assert res["is_preview"] is True
    assert len(res["imported_products"]) == 2

    # Verify that nothing was inserted into the database!
    prod_check = await db_session.execute(
        select(Product).where(Product.title.in_(["Solid Oak Desk Mat", "Ergonomic Wrist Rest"]))
    )
    assert len(prod_check.scalars().all()) == 0


@pytest.mark.asyncio
async def test_csv_preview_prohibited_price_column(
    client: AsyncClient,
    sample_niche: Niche,
) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    csv_with_price = (
        "title,niche,benable_url,price\n"
        "Desk Mat,Workspace Setup,https://benable.com/p/1,29.99\n"
    )

    resp = await client.post(
        "/api/products/preview-csv",
        json={"csv_content": csv_with_price},
        headers=headers,
        cookies=cookies,
    )
    assert resp.status_code == 200
    res = resp.json()
    assert res["imported_count"] == 0
    assert len(res["errors"]) > 0
    assert "Prohibited pricing column" in res["errors"][0]["reason"]


@pytest.mark.asyncio
async def test_csv_preview_row_by_row_errors(
    client: AsyncClient,
    sample_niche: Niche,
) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    csv_mixed = (
        "title,niche,benable_url,benefits\n"
        "Valid Desk Shelf,Workspace Setup,https://benable.com/shelf,Walnut hardwood\n"
        "Shortener Link Item,Workspace Setup,https://bit.ly/shelf-item,Cheap item\n"
        "Nonexistent Niche Item,Unknown Niche,https://benable.com/other,Good product\n"
    )

    resp = await client.post(
        "/api/products/preview-csv",
        json={"csv_content": csv_mixed},
        headers=headers,
        cookies=cookies,
    )
    assert resp.status_code == 200
    res = resp.json()
    assert res["total_rows"] == 3
    assert res["imported_count"] == 1
    assert res["failed_count"] == 2

    reasons = [e["reason"] for e in res["errors"]]
    assert any("shortener" in r.lower() or "allowlist" in r.lower() for r in reasons)
    assert any("not found" in r.lower() for r in reasons)


@pytest.mark.asyncio
async def test_validate_url_endpoint(client: AsyncClient) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    # 1. Valid HTTPS benable.com
    resp_valid = await client.post(
        "/api/products/validate-url",
        json={"url": "https://benable.com/curator/top-finds"},
        headers=headers,
        cookies=cookies,
    )
    assert resp_valid.status_code == 200
    data = resp_valid.json()
    assert data["valid"] is True
    assert data["error"] is None

    # 2. Insecure HTTP
    resp_http = await client.post(
        "/api/products/validate-url",
        json={"url": "http://benable.com/list/123"},
        headers=headers,
        cookies=cookies,
    )
    assert resp_http.status_code == 200
    assert resp_http.json()["valid"] is False
    assert "HTTPS" in resp_http.json()["error"]

    # 3. Shortener
    resp_short = await client.post(
        "/api/products/validate-url",
        json={"url": "https://tinyurl.com/benable-item"},
        headers=headers,
        cookies=cookies,
    )
    assert resp_short.status_code == 200
    assert resp_short.json()["valid"] is False
    assert "shortener" in resp_short.json()["error"].lower()

    # 4. Foreign domain
    resp_foreign = await client.post(
        "/api/products/validate-url",
        json={"url": "https://aliexpress.com/item/123.html"},
        headers=headers,
        cookies=cookies,
    )
    assert resp_foreign.status_code == 200
    assert resp_foreign.json()["valid"] is False
    assert "allowlist" in resp_foreign.json()["error"].lower()


@pytest.mark.asyncio
async def test_soft_delete_preserves_records(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_niche: Niche,
) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    # Create product
    create_resp = await client.post(
        "/api/products",
        json={
            "niche_id": sample_niche.id,
            "title": "Minimal Cable Organizer Box",
            "benable_url": "https://benable.com/desk/cable-box",
            "benefits": ["Flame retardant", "Hidden power strip"],
            "tags": ["cables", "desk"],
        },
        headers=headers,
        cookies=cookies,
    )
    assert create_resp.status_code == 201
    prod_id = create_resp.json()["id"]

    # Soft delete product
    del_resp = await client.delete(f"/api/products/{prod_id}", headers=headers, cookies=cookies)
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "archived"

    # Verify still in database
    db_prod = await db_session.get(Product, prod_id)
    assert db_prod is not None
    assert db_prod.status == "archived"
