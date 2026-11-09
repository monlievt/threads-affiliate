"""app/analytics/click_importer.py — Benable Link Clicks CSV Importer and Record Manager (T-041).

Safety & Attribution Principles:
1. Caveat Banner / Tooltip:
   "Data klik dari Benable hanya dapat diatribusikan ke produk + periode waktu,
    bukan ke post spesifik. Data klik menunjukkan performa produk dalam periode ini,
    bukan performa per post individual."
2. Row-by-row validation with detailed failure reporting.
3. Linking to existing Products and/or Posts.
4. Non-negative clicks constraint (clicks >= 0).
5. Chronological period constraint (period_start <= period_end).
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import LinkClick, Post, Product, utc_now_iso

CLICK_ATTRIBUTION_CAVEAT = (
    "Data klik dari Benable hanya dapat diatribusikan ke produk + periode waktu, "
    "bukan ke post spesifik. Data klik menunjukkan performa produk dalam periode ini, "
    "bukan performa per post individual."
)


def parse_date_str(val: str) -> datetime | None:
    """Safely parse date string in ISO format or YYYY-MM-DD."""
    if not val:
        return None
    cleaned = val.strip()
    # Try ISO format
    try:
        return datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except Exception:
        pass
    # Try YYYY-MM-DD
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(cleaned, fmt)
        except Exception:
            pass
    return None


async def parse_and_import_clicks_csv(
    csv_text: str,
    session: AsyncSession,
    dry_run: bool = False,
    default_source: str = "benable_csv",
) -> dict[str, Any]:
    """Parse CSV text containing Benable click data, validate row-by-row,

    and commit valid rows (or preview if dry_run=True).
    """
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    if not reader.fieldnames:
        return {
            "total_rows": 0,
            "imported_count": 0,
            "failed_count": 1,
            "is_preview": dry_run,
            "attribution_caveat": CLICK_ATTRIBUTION_CAVEAT,
            "errors": [{"row": 0, "product": None, "reason": "Empty CSV or missing headers."}],
            "imported_items": [],
        }

    # Normalize header mapping
    raw_fields = [f.strip() for f in reader.fieldnames if f]
    header_map: dict[str, str] = {}
    for f in raw_fields:
        f_lower = f.lower()
        if f_lower in ("product_id", "product", "product_title", "title"):
            header_map["product"] = f
        elif f_lower in ("post_id", "post"):
            header_map["post"] = f
        elif f_lower in ("period_start", "start_date", "start"):
            header_map["period_start"] = f
        elif f_lower in ("period_end", "end_date", "end"):
            header_map["period_end"] = f
        elif f_lower in ("clicks", "click_count", "count"):
            header_map["clicks"] = f
        elif f_lower in ("note", "notes"):
            header_map["note"] = f
        elif f_lower in ("source",):
            header_map["source"] = f

    if "period_start" not in header_map or "period_end" not in header_map or "clicks" not in header_map:
        return {
            "total_rows": 0,
            "imported_count": 0,
            "failed_count": 1,
            "is_preview": dry_run,
            "attribution_caveat": CLICK_ATTRIBUTION_CAVEAT,
            "errors": [
                {
                    "row": 0,
                    "product": None,
                    "reason": "Missing required CSV columns: 'period_start', 'period_end', and 'clicks'.",
                }
            ],
            "imported_items": [],
        }

    # Preload products and posts for quick lookups
    prod_res = await session.execute(select(Product))
    products = prod_res.scalars().all()
    product_by_id = {p.id: p for p in products}
    product_by_title = {p.title.strip().lower(): p for p in products}

    posts_res = await session.execute(select(Post))
    posts = posts_res.scalars().all()
    post_by_id = {p.id: p for p in posts}

    errors: list[dict[str, Any]] = []
    imported_models: list[LinkClick] = []
    total_rows = 0

    for idx, row in enumerate(reader, start=1):
        total_rows += 1
        raw_product = (row.get(header_map.get("product", "")) or "").strip()
        raw_post = (row.get(header_map.get("post", "")) or "").strip()
        raw_start = (row.get(header_map["period_start"]) or "").strip()
        raw_end = (row.get(header_map["period_end"]) or "").strip()
        raw_clicks = (row.get(header_map["clicks"]) or "").strip()
        note = (row.get(header_map.get("note", "")) or "").strip() or None
        source = (row.get(header_map.get("source", "")) or "").strip() or default_source

        # 1. Validate clicks
        try:
            clicks = int(raw_clicks)
            if clicks < 0:
                errors.append({"row": idx, "product": raw_product, "reason": "Clicks cannot be negative."})
                continue
        except (ValueError, TypeError):
            errors.append({"row": idx, "product": raw_product, "reason": f"Invalid click count '{raw_clicks}', must be integer."})
            continue

        # 2. Validate dates
        dt_start = parse_date_str(raw_start)
        dt_end = parse_date_str(raw_end)
        if not dt_start:
            errors.append({"row": idx, "product": raw_product, "reason": f"Invalid period_start date format '{raw_start}'."})
            continue
        if not dt_end:
            errors.append({"row": idx, "product": raw_product, "reason": f"Invalid period_end date format '{raw_end}'."})
            continue
        if dt_start > dt_end:
            errors.append({
                "row": idx,
                "product": raw_product,
                "reason": f"period_start ({raw_start}) cannot be after period_end ({raw_end}).",
            })
            continue

        # 3. Resolve product (if specified)
        matched_product: Product | None = None
        if raw_product:
            if raw_product in product_by_id:
                matched_product = product_by_id[raw_product]
            elif raw_product.lower() in product_by_title:
                matched_product = product_by_title[raw_product.lower()]
            else:
                errors.append({
                    "row": idx,
                    "product": raw_product,
                    "reason": f"Referenced product '{raw_product}' not found in catalog.",
                })
                continue

        # 4. Resolve post (if specified)
        matched_post: Post | None = None
        if raw_post:
            if raw_post in post_by_id:
                matched_post = post_by_id[raw_post]
            else:
                errors.append({
                    "row": idx,
                    "product": raw_product,
                    "reason": f"Referenced post ID '{raw_post}' not found.",
                })
                continue

        # At least product or post should be linked
        if not matched_product and not matched_post:
            errors.append({
                "row": idx,
                "product": None,
                "reason": "Row must specify at least one valid product or post reference.",
            })
            continue

        item = LinkClick(
            product_id=matched_product.id if matched_product else None,
            post_id=matched_post.id if matched_post else None,
            period_start=dt_start.isoformat(),
            period_end=dt_end.isoformat(),
            clicks=clicks,
            source=source,
            note=note,
        )
        item.product = matched_product
        item.post = matched_post

        if dry_run:
            item.id = f"preview_{idx}"
            item.created_at = utc_now_iso()
        else:
            session.add(item)

        imported_models.append(item)

    if not dry_run and imported_models:
        await session.commit()
        for m in imported_models:
            await session.refresh(m)

    items_repr = []
    for m in imported_models:
        items_repr.append({
            "id": m.id,
            "product_id": m.product_id,
            "product_title": m.product.title if m.product else None,
            "post_id": m.post_id,
            "period_start": m.period_start,
            "period_end": m.period_end,
            "clicks": m.clicks,
            "source": m.source,
            "note": m.note,
            "created_at": m.created_at,
        })

    return {
        "total_rows": total_rows,
        "imported_count": len(imported_models),
        "failed_count": len(errors),
        "is_preview": dry_run,
        "attribution_caveat": CLICK_ATTRIBUTION_CAVEAT,
        "errors": errors,
        "imported_items": items_repr,
    }
