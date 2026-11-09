"""app/api/products.py — CRUD endpoints and CSV importer for Affiliate Products.

Follows strict safety principles:
- Allowlist domain validation for benable_url (benable.com HTTPS only, no shorteners).
- Zero price policy (V-PRICE: rejects currency symbols, discounts, sales, and pricing numbers).
- No hard delete: DELETE endpoints perform soft-delete by setting status = 'archived'.
- Row-by-row CSV validation with detailed error reporting.
- All mutations require admin session + CSRF token, and append an audit log entry.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import record_audit_log
from app.core.security import get_current_admin, require_csrf
from app.db.models import Niche, Product, utc_now_iso
from app.db.session import get_db
from app.safety.catalog_rules import (
    PROHIBITED_CSV_HEADERS,
    validate_product_benable_url,
    validate_product_text_safety,
)
from app.schemas.catalog import (
    CSVImportRowError,
    ProductCreate,
    ProductImportResponse,
    ProductResponse,
    ProductUpdate,
)

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("", response_model=list[ProductResponse])
async def list_products(
    niche_id: str | None = Query(default=None, description="Filter by niche ID"),
    status_filter: str | None = Query(default=None, alias="status", description="Filter by status"),
    include_archived: bool = Query(default=False, description="Include archived products"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> list[ProductResponse]:
    """List products with optional niche, status, and pagination filters."""
    query = select(Product).options(selectinload(Product.niche))

    if niche_id:
        query = query.where(Product.niche_id == niche_id)

    if status_filter:
        query = query.where(Product.status == status_filter)
    elif not include_archived:
        query = query.where(Product.status != "archived")

    query = query.order_by(Product.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(query)
    products = result.scalars().all()
    return [ProductResponse.from_orm_model(p) for p in products]


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),  # noqa: ARG001
) -> ProductResponse:
    """Get single product by ID."""
    result = await session.execute(
        select(Product).options(selectinload(Product.niche)).where(Product.id == product_id)
    )
    prod = result.scalar_one_or_none()
    if not prod:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {product_id!r} not found.",
        )
    return ProductResponse.from_orm_model(prod)


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> ProductResponse:
    """Create a new affiliate product after safety checks."""
    # 1. URL Allowlist check
    valid_url, url_err = validate_product_benable_url(payload.benable_url)
    if not valid_url:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=url_err)

    # 2. V-PRICE zero-price policy check
    valid_text, text_err = validate_product_text_safety(
        title=payload.title,
        benefits=payload.benefits,
        tags=payload.tags,
    )
    if not valid_text:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=text_err)

    # 3. Niche must exist and not be archived
    niche_res = await session.execute(select(Niche).where(Niche.id == payload.niche_id))
    niche = niche_res.scalar_one_or_none()
    if not niche:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Niche with ID {payload.niche_id!r} does not exist.",
        )
    if niche.status == "archived":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot associate product with archived niche {niche.name!r}.",
        )

    benefits_json = json.dumps(payload.benefits) if payload.benefits else None
    tags_json = json.dumps(payload.tags) if payload.tags else None

    product = Product(
        niche_id=payload.niche_id,
        title=payload.title,
        benable_url=payload.benable_url,
        amazon_ref_url=payload.amazon_ref_url,
        benefits=benefits_json,
        tags=tags_json,
        status="active",
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)

    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="create",
        entity="products",
        entity_id=product.id,
        detail={"title": product.title, "niche_id": product.niche_id},
    )

    return ProductResponse.from_orm_model(product, niche_name=niche.name)


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str,
    payload: ProductUpdate,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> ProductResponse:
    """Update existing product with full safety checks."""
    result = await session.execute(
        select(Product).options(selectinload(Product.niche)).where(Product.id == product_id)
    )
    prod = result.scalar_one_or_none()
    if not prod:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {product_id!r} not found.",
        )

    # 1. URL validation if updated
    if payload.benable_url is not None:
        valid_url, url_err = validate_product_benable_url(payload.benable_url)
        if not valid_url:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=url_err)
        prod.benable_url = payload.benable_url

    # 2. Text safety validation if text changed
    title_check = payload.title if payload.title is not None else prod.title
    benefits_check = (
        payload.benefits
        if payload.benefits is not None
        else (json.loads(prod.benefits) if prod.benefits else None)
    )
    tags_check = (
        payload.tags
        if payload.tags is not None
        else (json.loads(prod.tags) if prod.tags else None)
    )

    valid_text, text_err = validate_product_text_safety(
        title=title_check,
        benefits=benefits_check,
        tags=tags_check,
    )
    if not valid_text:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=text_err)

    if payload.title is not None:
        prod.title = payload.title
    if payload.benefits is not None:
        prod.benefits = json.dumps(payload.benefits)
    if payload.tags is not None:
        prod.tags = json.dumps(payload.tags)
    if payload.amazon_ref_url is not None:
        prod.amazon_ref_url = payload.amazon_ref_url
    if payload.status is not None:
        prod.status = payload.status

    if payload.niche_id is not None and payload.niche_id != prod.niche_id:
        niche_res = await session.execute(select(Niche).where(Niche.id == payload.niche_id))
        niche = niche_res.scalar_one_or_none()
        if not niche:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Niche with ID {payload.niche_id!r} not found.",
            )
        prod.niche_id = payload.niche_id

    prod.updated_at = utc_now_iso()
    await session.commit()
    await session.refresh(prod)

    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="update",
        entity="products",
        entity_id=prod.id,
        detail={"updated_fields": payload.model_dump(exclude_unset=True)},
    )

    return ProductResponse.from_orm_model(prod)


@router.delete("/{product_id}", response_model=ProductResponse)
async def delete_product(
    product_id: str,
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> ProductResponse:
    """Soft-delete a product (sets status = 'archived'). Hard delete is prohibited."""
    result = await session.execute(
        select(Product).options(selectinload(Product.niche)).where(Product.id == product_id)
    )
    prod = result.scalar_one_or_none()
    if not prod:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {product_id!r} not found.",
        )

    prod.status = "archived"
    prod.updated_at = utc_now_iso()
    await session.commit()
    await session.refresh(prod)

    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="archive",
        entity="products",
        entity_id=prod.id,
        detail={"title": prod.title, "status": "archived"},
    )

    return ProductResponse.from_orm_model(prod)


# ---------------------------------------------------------------------------
# CSV Importer
# ---------------------------------------------------------------------------
async def _parse_and_import_csv(
    csv_text: str,
    session: AsyncSession,
) -> ProductImportResponse:
    """Parse CSV text, enforce safety rules, and insert valid products."""
    # Pre-load all niches into a lookup cache (by ID and lowercased name)
    niches_res = await session.execute(select(Niche).where(Niche.status != "archived"))
    active_niches = niches_res.scalars().all()
    niche_by_id = {n.id: n for n in active_niches}
    niche_by_name = {n.name.lower().strip(): n for n in active_niches}

    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    if not reader.fieldnames:
        return ProductImportResponse(
            total_rows=0,
            imported_count=0,
            failed_count=0,
            errors=[CSVImportRowError(row=0, reason="Empty CSV file or missing headers.")],
        )

    # Normalize header names (lowercase, stripped)
    clean_fieldnames = [f.strip().lower() for f in reader.fieldnames if f]

    # Prohibited columns check (price, discount, etc.)
    prohibited_found = set(clean_fieldnames).intersection(PROHIBITED_CSV_HEADERS)
    if prohibited_found:
        return ProductImportResponse(
            total_rows=0,
            imported_count=0,
            failed_count=0,
            errors=[
                CSVImportRowError(
                    row=0,
                    reason=f"Prohibited pricing column(s) detected in CSV: {sorted(prohibited_found)}. Affiliate products must have no price claims.",
                )
            ],
        )

    # Required headers
    has_title = "title" in clean_fieldnames
    has_niche = "niche" in clean_fieldnames or "niche_id" in clean_fieldnames or "niche_name" in clean_fieldnames
    has_url = "benable_url" in clean_fieldnames or "url" in clean_fieldnames

    if not (has_title and has_niche and has_url):
        missing: list[str] = []
        if not has_title:
            missing.append("title")
        if not has_niche:
            missing.append("niche/niche_id")
        if not has_url:
            missing.append("benable_url")
        return ProductImportResponse(
            total_rows=0,
            imported_count=0,
            failed_count=0,
            errors=[CSVImportRowError(row=0, reason=f"Missing required columns in CSV header: {', '.join(missing)}.")],
        )

    total_rows = 0
    imported: list[Product] = []
    errors: list[CSVImportRowError] = []

    for row_idx, raw_row in enumerate(reader, start=1):
        total_rows += 1
        # Normalize keys in row
        row = {k.strip().lower(): v.strip() for k, v in raw_row.items() if k is not None and v is not None}

        title = row.get("title", "")
        if not title:
            errors.append(CSVImportRowError(row=row_idx, title=title, reason="Product title cannot be empty."))
            continue

        # Niche lookup
        niche_key = row.get("niche") or row.get("niche_id") or row.get("niche_name") or ""
        matched_niche = niche_by_id.get(niche_key) or niche_by_name.get(niche_key.lower())
        if not matched_niche:
            errors.append(
                CSVImportRowError(
                    row=row_idx,
                    title=title,
                    reason=f"Niche {niche_key!r} not found or is archived.",
                )
            )
            continue

        # Benable URL validation
        benable_url = row.get("benable_url") or row.get("url") or ""
        valid_url, url_err = validate_product_benable_url(benable_url)
        if not valid_url:
            errors.append(CSVImportRowError(row=row_idx, title=title, reason=url_err or "Invalid URL"))
            continue

        # Parse benefits and tags
        raw_benefits = row.get("benefits", "")
        benefits_list = [b.strip() for b in re.split(r"[;\n]", raw_benefits) if b.strip()] if raw_benefits else []

        raw_tags = row.get("tags", "")
        tags_list = [t.strip() for t in re.split(r"[,;\n]", raw_tags) if t.strip()] if raw_tags else []

        amazon_ref = row.get("amazon_ref_url") or row.get("amazon_url") or None

        # Text safety check (V-PRICE)
        valid_text, text_err = validate_product_text_safety(
            title=title,
            benefits=benefits_list or None,
            tags=tags_list or None,
        )
        if not valid_text:
            errors.append(CSVImportRowError(row=row_idx, title=title, reason=text_err or "Price violation"))
            continue

        prod = Product(
            niche_id=matched_niche.id,
            title=title,
            benable_url=benable_url,
            amazon_ref_url=amazon_ref,
            benefits=json.dumps(benefits_list) if benefits_list else None,
            tags=json.dumps(tags_list) if tags_list else None,
            status="active",
        )
        session.add(prod)
        imported.append(prod)

    if imported:
        await session.commit()
        for p in imported:
            await session.refresh(p)

    return ProductImportResponse(
        total_rows=total_rows,
        imported_count=len(imported),
        failed_count=len(errors),
        errors=errors,
        imported_products=[ProductResponse.from_orm_model(p) for p in imported],
    )


@router.post("/import-csv", response_model=ProductImportResponse)
async def import_products_csv(
    file: UploadFile | None = File(default=None),
    csv_content: str | None = Body(default=None, embed=True),
    session: AsyncSession = Depends(get_db),
    admin: dict[str, Any] = Depends(get_current_admin),
    _csrf: None = Depends(require_csrf),  # noqa: ARG001
) -> ProductImportResponse:
    """Import affiliate products from CSV with per-row validation and error reporting.

    Accepts either multipart file upload or JSON payload with `csv_content`.
    """
    raw_text = ""
    if file:
        content_bytes = await file.read()
        try:
            raw_text = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raw_text = content_bytes.decode("latin-1")
    elif csv_content:
        raw_text = csv_content
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either a CSV file or csv_content text must be provided.",
        )

    result = await _parse_and_import_csv(raw_text, session)

    # Log audit event
    await record_audit_log(
        session,
        actor=admin.get("sub", "admin"),
        action="import_csv",
        entity="products",
        detail={
            "total_rows": result.total_rows,
            "imported_count": result.imported_count,
            "failed_count": result.failed_count,
        },
    )

    return result
