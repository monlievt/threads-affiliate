"""app/schemas/catalog.py — Pydantic schemas for catalog entities and CSV import.

Entities:
- Niches
- Products
- Styles
- Personas
"""

from __future__ import annotations

import json
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Niches
# ---------------------------------------------------------------------------
class NicheBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Unique niche name")
    description: str | None = Field(default=None, max_length=500)
    keywords: list[str] | None = Field(default=None, description="Keywords for the niche")


class NicheCreate(NicheBase):
    pass


class NicheUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    keywords: list[str] | None = None
    status: Literal["active", "paused", "archived"] | None = None


class NicheResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    keywords: list[str] = Field(default_factory=list)
    status: str
    created_at: str
    updated_at: str

    @classmethod
    def from_orm_model(cls, obj: Any) -> NicheResponse:
        keywords_val: list[str] = []
        if obj.keywords:
            try:
                parsed = json.loads(obj.keywords)
                if isinstance(parsed, list):
                    keywords_val = parsed
            except (json.JSONDecodeError, TypeError):
                keywords_val = []

        return cls(
            id=obj.id,
            name=obj.name,
            description=obj.description,
            keywords=keywords_val,
            status=obj.status,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------
class ProductBase(BaseModel):
    niche_id: str = Field(..., description="Target niche UUID")
    title: str = Field(..., min_length=2, max_length=255, description="Product title without price claims")
    benable_url: str = Field(..., description="HTTPS link to Benable product/list")
    amazon_ref_url: str | None = Field(default=None, description="Internal reference URL only (not published)")
    benefits: list[str] | None = Field(default=None, description="Feature/benefit bullet points without prices")
    tags: list[str] | None = Field(default=None, description="Category/tag keywords")


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    niche_id: str | None = None
    title: str | None = Field(default=None, min_length=2, max_length=255)
    benable_url: str | None = None
    amazon_ref_url: str | None = None
    benefits: list[str] | None = None
    tags: list[str] | None = None
    status: Literal["active", "paused", "archived"] | None = None


class ProductResponse(BaseModel):
    id: str
    niche_id: str
    niche_name: str | None = None
    title: str
    benable_url: str
    amazon_ref_url: str | None = None
    benefits: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    status: str
    last_used_at: str | None = None
    created_at: str
    updated_at: str

    @classmethod
    def from_orm_model(cls, obj: Any, niche_name: str | None = None) -> ProductResponse:
        benefits_val: list[str] = []
        if obj.benefits:
            try:
                parsed = json.loads(obj.benefits)
                if isinstance(parsed, list):
                    benefits_val = parsed
            except (json.JSONDecodeError, TypeError):
                benefits_val = []

        tags_val: list[str] = []
        if obj.tags:
            try:
                parsed = json.loads(obj.tags)
                if isinstance(parsed, list):
                    tags_val = parsed
            except (json.JSONDecodeError, TypeError):
                tags_val = []

        return cls(
            id=obj.id,
            niche_id=obj.niche_id,
            niche_name=niche_name or (obj.niche.name if getattr(obj, "niche", None) else None),
            title=obj.title,
            benable_url=obj.benable_url,
            amazon_ref_url=obj.amazon_ref_url,
            benefits=benefits_val,
            tags=tags_val,
            status=obj.status,
            last_used_at=obj.last_used_at,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class CSVImportRowError(BaseModel):
    row: int
    title: str | None = None
    reason: str


class ProductImportResponse(BaseModel):
    total_rows: int
    imported_count: int
    failed_count: int
    is_preview: bool = False
    errors: list[CSVImportRowError] = Field(default_factory=list)
    imported_products: list[ProductResponse] = Field(default_factory=list)


class ValidateUrlRequest(BaseModel):
    url: str = Field(..., description="URL to validate for Benable allowlist")


class ValidateUrlResponse(BaseModel):
    url: str
    valid: bool
    error: str | None = None
    normalized_url: str | None = None


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------
class StyleBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=50, description="Unique style slug (e.g. curator, quick_review)")
    description: str = Field(..., min_length=5, description="High-level description of style purpose")
    tone_rules: str = Field(..., min_length=10, description="Guidelines for prompt generation")
    max_chars: int = Field(default=400, ge=100, le=500, description="Target character ceiling")
    good_examples: list[str] | None = None
    bad_examples: list[str] | None = None


class StyleCreate(StyleBase):
    pass


class StyleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=50)
    description: str | None = None
    tone_rules: str | None = None
    max_chars: int | None = Field(default=None, ge=100, le=500)
    good_examples: list[str] | None = None
    bad_examples: list[str] | None = None
    status: Literal["active", "paused", "archived"] | None = None


class StyleResponse(BaseModel):
    id: str
    name: str
    description: str
    tone_rules: str
    max_chars: int
    good_examples: list[str] = Field(default_factory=list)
    bad_examples: list[str] = Field(default_factory=list)
    status: str
    created_at: str
    updated_at: str

    @classmethod
    def from_orm_model(cls, obj: Any) -> StyleResponse:
        good: list[str] = []
        if obj.good_examples:
            try:
                parsed = json.loads(obj.good_examples)
                if isinstance(parsed, list):
                    good = parsed
            except (json.JSONDecodeError, TypeError):
                good = []

        bad: list[str] = []
        if obj.bad_examples:
            try:
                parsed = json.loads(obj.bad_examples)
                if isinstance(parsed, list):
                    bad = parsed
            except (json.JSONDecodeError, TypeError):
                bad = []

        return cls(
            id=obj.id,
            name=obj.name,
            description=obj.description,
            tone_rules=obj.tone_rules,
            max_chars=obj.max_chars,
            good_examples=good,
            bad_examples=bad,
            status=obj.status,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------
class PersonaBase(BaseModel):
    account_id: str = Field(..., description="Target account UUID")
    name: str = Field(..., min_length=2, max_length=100)
    voice: str = Field(..., min_length=5, description="Persona voice and characteristics")
    avoid: str | None = Field(default=None, description="Prohibited persona traits")
    disclosure_text: str = Field(default="Affiliate link", min_length=3, max_length=100)
    disclosure_position: Literal["start", "end"] = Field(default="end")

    @field_validator("disclosure_text")
    @classmethod
    def validate_disclosure_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Disclosure text cannot be empty or whitespace.")
        return stripped


class PersonaCreate(PersonaBase):
    pass


class PersonaUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    voice: str | None = None
    avoid: str | None = None
    disclosure_text: str | None = Field(default=None, min_length=3, max_length=100)
    disclosure_position: Literal["start", "end"] | None = None


class PersonaResponse(BaseModel):
    id: str
    account_id: str
    name: str
    voice: str
    avoid: str | None = None
    disclosure_text: str
    disclosure_position: str
    created_at: str
    updated_at: str

    @classmethod
    def from_orm_model(cls, obj: Any) -> PersonaResponse:
        return cls(
            id=obj.id,
            account_id=obj.account_id,
            name=obj.name,
            voice=obj.voice,
            avoid=obj.avoid,
            disclosure_text=obj.disclosure_text,
            disclosure_position=obj.disclosure_position,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )
