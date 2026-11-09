"""app/telegram/formatter.py — Formatters for draft review cards and alert notifications."""

from __future__ import annotations

import json
from typing import Any
from app.db.models import Draft


def format_draft_card(
    draft: Draft,
    niche_name: str | None = None,
    style_name: str | None = None,
    slot_label: str | None = None,
    similarity_pct: float | None = None,
    version: str = "v1",
) -> tuple[str, list[list[dict[str, str]]]]:
    """Format draft review message and inline keyboard buttons according to specification.

    Format:
    📝 Draft #123 · Niche: Home&Kitchen · Style: curator · Slot: 14:30 EST
    ────────
    <teks draf>
    ────────
    Link: benable.com/... · Validator: ✅ semua lolos · Mirip terdekat: 41%
    """
    niche_display = niche_name or (draft.niche.name if getattr(draft, "niche", None) else "General")
    style_display = style_name or (draft.style.name if getattr(draft, "style", None) else "Default")
    slot_display = slot_label or (draft.scheduled_at[11:16] if draft.scheduled_at and len(draft.scheduled_at) >= 16 else "Unscheduled")

    # Extract draft text content
    content_lines: list[str] = []
    if draft.parts:
        try:
            parts = json.loads(draft.parts)
            if isinstance(parts, list):
                content_lines = [p.get("text", "") for p in parts if isinstance(p, dict)]
        except Exception:
            content_lines = [draft.parts]
    else:
        content_lines = ["(No content)"]

    content_text = "\n\n".join(content_lines)

    # Link info
    link_info = draft.link_url if draft.link_url else "None (Organic Post)"

    # Validator status
    val_status = "✅ semua lolos" if draft.status != "rejected_auto" else "❌ aturan dilanggar"

    # Similarity info
    sim_display = f"{int(similarity_pct)}%" if similarity_pct is not None else "N/A"

    # Short draft ID (8 chars)
    short_id = draft.id[:8]

    text = (
        f"📝 <b>Draft #{short_id}</b> · Niche: {niche_display} · Style: {style_display} · Slot: {slot_display}\n"
        f"────────\n"
        f"{content_text}\n"
        f"────────\n"
        f"🔗 Link: <code>{link_info}</code>\n"
        f"🛡️ Validator: {val_status} · Mirip terdekat: {sim_display}"
    )

    # Inline Keyboard Buttons with idempotency callback data: draft:{id}:{action}:{version}
    buttons = [
        [
            {"text": "✅ Setujui", "callback_data": f"draft:{draft.id}:approve:{version}"},
            {"text": "❌ Tolak", "callback_data": f"draft:{draft.id}:reject:{version}"},
        ],
        [
            {"text": "🔁 Regenerasi", "callback_data": f"draft:{draft.id}:regenerate:{version}"},
        ],
    ]

    return text, buttons


def format_critical_alert(message: str) -> str:
    """Format critical system alert with 🚨 emoji prefix."""
    return f"🚨 <b>SYSTEM ALERT</b>\n\n{message}"
