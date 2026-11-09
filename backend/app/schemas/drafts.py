"""app/schemas/drafts.py — Pydantic schemas for Draft management and validation."""

from __future__ import annotations

import json
from typing import Any
from pydantic import BaseModel, Field


class DraftPart(BaseModel):
    part_index: int = 1
    text: str
    char_count: int | None = None


class DraftResponse(BaseModel):
    id: str
    account_id: str
    kind: str
    niche_id: str | None = None
    niche_name: str | None = None
    style_id: str | None = None
    style_name: str | None = None
    product_id: str | None = None
    product_title: str | None = None
    prompt_version: str
    llm_model: str
    parts: list[dict[str, Any]] = Field(default_factory=list)
    text: str = ""
    link_url: str | None = None
    link_placement: str | None = None
    status: str
    reject_reason: str | None = None
    validator_report: dict[str, Any] | None = None
    similarity_score: float | None = None
    text_hash: str
    scheduled_at: str | None = None
    reviewed_at: str | None = None
    expires_at: str | None = None
    created_at: str
    updated_at: str

    @classmethod
    def from_orm_model(cls, obj: Any) -> DraftResponse:
        parsed_parts: list[dict[str, Any]] = []
        raw_text = ""
        if obj.parts:
            try:
                data = json.loads(obj.parts)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            parsed_parts.append(item)
                            if not raw_text:
                                raw_text = item.get("text", "")
                        elif isinstance(item, str):
                            parsed_parts.append({"text": item})
                            if not raw_text:
                                raw_text = item
                elif isinstance(data, str):
                    parsed_parts = [{"text": data}]
                    raw_text = data
            except Exception:
                parsed_parts = [{"text": str(obj.parts)}]
                raw_text = str(obj.parts)

        parsed_report: dict[str, Any] | None = None
        if obj.validator_report:
            try:
                parsed_report = json.loads(obj.validator_report)
            except Exception:
                parsed_report = None

        return cls(
            id=obj.id,
            account_id=obj.account_id,
            kind=obj.kind,
            niche_id=obj.niche_id,
            niche_name=obj.niche.name if getattr(obj, "niche", None) else None,
            style_id=obj.style_id,
            style_name=obj.style.name if getattr(obj, "style", None) else None,
            product_id=obj.product_id,
            product_title=obj.product.title if getattr(obj, "product", None) else None,
            prompt_version=obj.prompt_version,
            llm_model=obj.llm_model,
            parts=parsed_parts,
            text=raw_text,
            link_url=obj.link_url,
            link_placement=obj.link_placement,
            status=obj.status,
            reject_reason=obj.reject_reason,
            validator_report=parsed_report,
            text_hash=obj.text_hash,
            scheduled_at=obj.scheduled_at,
            reviewed_at=obj.reviewed_at,
            expires_at=obj.expires_at,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class DraftEditRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000, description="Updated post body")
    scheduled_at: str | None = Field(default=None, description="Optional custom slot")


class DraftRejectRequest(BaseModel):
    reason: str | None = Field(default=None, description="Optional rejection feedback")


class ValidateTextRequest(BaseModel):
    text: str = Field(..., description="Post content text to validate in real-time")
    style_id: str | None = None
    is_affiliate: bool = True
    disclosure_text: str = "Affiliate link"


class RuleValidationItem(BaseModel):
    code: str
    valid: bool
    reason: str | None = None


class ValidateTextResponse(BaseModel):
    valid: bool
    char_count: int
    max_chars: int
    failed_codes: list[str]
    results: dict[str, RuleValidationItem]


class BatchApproveResponse(BaseModel):
    total_eligible: int
    approved_count: int
    approved_ids: list[str]
