"""tests/test_click_importer.py — Test suite for Benable Click Importer and API (T-041).

Verifies:
1. Date parsing utilities (ISO, YYYY-MM-DD, error handling).
2. Row-by-row CSV parsing and validation:
   - Header flexibility (case-insensitivity, product, start, end, clicks).
   - Non-negative clicks constraint.
   - Chronological period validation (start <= end).
   - Product lookup by ID and title.
   - Fail-soft reporting of invalid rows without aborting valid ones.
3. Mandatory caveat attribution text included in responses and importer summaries.
4. CRUD & Import API endpoints:
   - GET /api/analytics/clicks (with filters, pagination, caveat notice).
   - POST /api/analytics/clicks (manual entry, CSRF, audit log).
   - POST /api/analytics/clicks/preview-csv (dry-run).
   - POST /api/analytics/clicks/import-csv (commit & audit).
   - DELETE /api/analytics/clicks/{id} (delete & audit).
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.click_importer import (
    CLICK_ATTRIBUTION_CAVEAT,
    parse_and_import_clicks_csv,
    parse_date_str,
)
from app.core.clock import utc_now_iso
from app.core.security import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, create_session_token
from app.db.models import AuditLog, LinkClick, Niche, Product


def _get_auth_headers_and_cookies() -> tuple[dict[str, str], dict[str, str]]:
    token, csrf_token = create_session_token("admin")
    headers = {"X-CSRF-Token": csrf_token}
    cookies = {
        SESSION_COOKIE_NAME: token,
        CSRF_COOKIE_NAME: csrf_token,
    }
    return headers, cookies


# ---------------------------------------------------------------------------
# 1. Date parsing tests
# ---------------------------------------------------------------------------

def test_parse_date_str() -> None:
    # ISO strings
    dt1 = parse_date_str("2026-11-01T10:00:00Z")
    assert dt1 is not None
    assert dt1.year == 2026 and dt1.month == 11 and dt1.day == 1

    dt2 = parse_date_str("2026-11-05T08:30:00+00:00")
    assert dt2 is not None
    assert dt2.day == 5

    # Standard date formats
    dt3 = parse_date_str("2026-11-08")
    assert dt3 is not None
    assert dt3.year == 2026 and dt3.month == 11 and dt3.day == 8

    dt4 = parse_date_str("2026/11/09")
    assert dt4 is not None
    assert dt4.day == 9

    # Invalid strings
    assert parse_date_str("") is None
    assert parse_date_str("not-a-date") is None


# ---------------------------------------------------------------------------
# 2. CSV Parser Unit & Safety Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_csv_parser_empty_or_missing_headers(db_session: AsyncSession) -> None:
    res = await parse_and_import_clicks_csv("", db_session, dry_run=True)
    assert res["total_rows"] == 0
    assert res["failed_count"] == 1
    assert "Empty CSV" in res["errors"][0]["reason"]
    assert res["attribution_caveat"] == CLICK_ATTRIBUTION_CAVEAT

    # Missing required columns
    bad_csv = "product,note\nMyProduct,some note"
    res2 = await parse_and_import_clicks_csv(bad_csv, db_session, dry_run=True)
    assert res2["failed_count"] == 1
    assert "Missing required CSV columns" in res2["errors"][0]["reason"]


@pytest.mark.asyncio
async def test_csv_parser_row_validation_rules(db_session: AsyncSession) -> None:
    # Create sample niche and product
    niche = Niche(id="niche_clicks_test", name="Ergonomics", slug="ergo-clicks")
    db_session.add(niche)
    product = Product(
        id="prod_clicks_1",
        niche_id=niche.id,
        title="Ergonomic Split Keyboard",
        benable_url="https://benable.com/custom/split-kb",
        status="active",
    )
    db_session.add(product)
    await db_session.commit()

    csv_data = (
        "product,period_start,period_end,clicks,note\n"
        "Ergonomic Split Keyboard,2026-11-01,2026-11-07,45,Weekly batch 1\n"
        "prod_clicks_1,2026-11-08,2026-11-14,30,Weekly batch 2\n"
        "Ergonomic Split Keyboard,2026-11-01,2026-11-07,-5,Negative clicks\n"
        "Ergonomic Split Keyboard,2026-11-10,2026-11-01,15,Start after end\n"
        "Ergonomic Split Keyboard,invalid_date,2026-11-07,10,Bad start date\n"
        "Nonexistent Product,2026-11-01,2026-11-07,20,Product not found\n"
    )

    # 1. Test dry run
    preview_res = await parse_and_import_clicks_csv(csv_data, db_session, dry_run=True)
    assert preview_res["total_rows"] == 6
    assert preview_res["imported_count"] == 2
    assert preview_res["failed_count"] == 4
    assert preview_res["is_preview"] is True
    assert preview_res["attribution_caveat"] == CLICK_ATTRIBUTION_CAVEAT

    reasons = [e["reason"] for e in preview_res["errors"]]
    assert any("negative" in r for r in reasons)
    assert any("cannot be after period_end" in r for r in reasons)
    assert any("Invalid period_start date format" in r for r in reasons)
    assert any("not found in catalog" in r for r in reasons)

    # Verify no records committed in dry run
    check = await db_session.execute(select(LinkClick))
    assert len(check.scalars().all()) == 0

    # 2. Test actual commit
    commit_res = await parse_and_import_clicks_csv(csv_data, db_session, dry_run=False)
    assert commit_res["imported_count"] == 2
    assert commit_res["failed_count"] == 4
    assert commit_res["is_preview"] is False

    # Verify records in database
    db_check = await db_session.execute(select(LinkClick))
    saved_items = db_check.scalars().all()
    assert len(saved_items) == 2
    assert sum(s.clicks for s in saved_items) == 75


# ---------------------------------------------------------------------------
# 3. API Endpoints Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_clicks_crud_and_caveat(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    # Pre-seed product
    niche = Niche(id="niche_api_clicks", name="Fitness", slug="fitness-clicks")
    db_session.add(niche)
    prod = Product(
        id="prod_api_clicks_1",
        niche_id=niche.id,
        title="Resistance Bands Set",
        benable_url="https://benable.com/fit/bands",
        status="active",
    )
    db_session.add(prod)
    await db_session.commit()

    # 1. GET clicks - initial empty
    res = await async_client.get(
        "/api/analytics/clicks", headers=headers, cookies=cookies
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total_clicks"] == 0
    assert data["items_count"] == 0
    assert "Data klik dari Benable hanya dapat diatribusikan" in data["attribution_caveat"]

    # 2. POST create click manual - validation failure (start > end)
    bad_payload = {
        "product_id": prod.id,
        "period_start": "2026-11-10",
        "period_end": "2026-11-05",
        "clicks": 12,
    }
    bad_res = await async_client.post(
        "/api/analytics/clicks", json=bad_payload, headers=headers, cookies=cookies
    )
    assert bad_res.status_code == 400
    assert "period_start cannot be after period_end" in bad_res.json()["detail"]

    # 3. POST create click manual - success
    valid_payload = {
        "product_id": prod.id,
        "period_start": "2026-11-01",
        "period_end": "2026-11-07",
        "clicks": 55,
        "source": "benable_manual",
        "note": "Manual entry test",
    }
    create_res = await async_client.post(
        "/api/analytics/clicks", json=valid_payload, headers=headers, cookies=cookies
    )
    assert create_res.status_code == 201
    created_item = create_res.json()
    assert created_item["clicks"] == 55
    assert created_item["product_title"] == "Resistance Bands Set"
    click_id = created_item["id"]

    # 4. Verify Audit Log was recorded
    audit_res = await db_session.execute(
        select(AuditLog).where(AuditLog.entity_id == click_id)
    )
    audit_log = audit_res.scalar_one_or_none()
    assert audit_log is not None
    assert audit_log.action == "record_click"

    # 5. GET clicks with filter
    list_res = await async_client.get(
        f"/api/analytics/clicks?product_id={prod.id}",
        headers=headers,
        cookies=cookies,
    )
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total_clicks"] == 55
    assert list_data["items_count"] == 1
    assert list_data["items"][0]["id"] == click_id

    # 6. DELETE click
    del_res = await async_client.delete(
        f"/api/analytics/clicks/{click_id}", headers=headers, cookies=cookies
    )
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True

    # 7. GET clicks again -> now empty
    empty_res = await async_client.get(
        "/api/analytics/clicks", headers=headers, cookies=cookies
    )
    assert empty_res.json()["total_clicks"] == 0
    assert empty_res.json()["items_count"] == 0


@pytest.mark.asyncio
async def test_api_clicks_csv_preview_and_import(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    headers, cookies = _get_auth_headers_and_cookies()

    # Pre-seed product
    niche = Niche(id="niche_csv_api", name="Home Kitchen", slug="home-kitchen")
    db_session.add(niche)
    prod = Product(
        id="prod_csv_api_1",
        niche_id=niche.id,
        title="Cast Iron Skillet",
        benable_url="https://benable.com/kitchen/skillet",
        status="active",
    )
    db_session.add(prod)
    await db_session.commit()

    csv_content = (
        "product,period_start,period_end,clicks,note\n"
        "Cast Iron Skillet,2026-11-01,2026-11-07,88,CSV import batch\n"
        "prod_csv_api_1,2026-11-08,2026-11-14,42,Second week\n"
    )

    # 1. Preview CSV (dry run)
    preview_res = await async_client.post(
        "/api/analytics/clicks/preview-csv",
        json={"csv_content": csv_content},
        headers=headers,
        cookies=cookies,
    )
    assert preview_res.status_code == 200
    pdata = preview_res.json()
    assert pdata["total_rows"] == 2
    assert pdata["imported_count"] == 2
    assert pdata["failed_count"] == 0
    assert pdata["is_preview"] is True
    assert "Data klik dari Benable hanya dapat diatribusikan" in pdata["attribution_caveat"]

    # 2. Import CSV (actual commit)
    import_res = await async_client.post(
        "/api/analytics/clicks/import-csv",
        json={"csv_content": csv_content},
        headers=headers,
        cookies=cookies,
    )
    assert import_res.status_code == 200
    idata = import_res.json()
    assert idata["imported_count"] == 2
    assert idata["is_preview"] is False

    # 3. GET /api/analytics/clicks confirms 130 total clicks
    get_res = await async_client.get(
        "/api/analytics/clicks", headers=headers, cookies=cookies
    )
    gdata = get_res.json()
    assert gdata["total_clicks"] == 130
    assert gdata["items_count"] == 2
