"""app/safety — System safety, guard, rate governor, warmup schedule, validators, similarity, and kill switch."""

from app.safety.governor import (
    GovernorDecision,
    apply_jitter,
    check_governor_limits,
    get_target_day_bounds_utc,
    is_within_active_hours,
)
from app.safety.guard import GuardDecision, PublishGuard
from app.safety.killswitch import (
    ensure_kill_switch_initialized,
    get_kill_switch_status,
    is_kill_switch_active,
    set_kill_switch,
)
from app.safety.minimal_guard import check_minimal_guard
from app.safety.similarity import (
    SimilarityCheckResult,
    calculate_similarity,
    check_content_similarity,
    check_draft_similarity_in_db,
    compute_normalized_hash,
    normalize_text,
)
from app.safety.validators import (
    ValidationResult,
    ValidatorReport,
    validate_content,
    validate_v_claim,
    validate_v_disc,
    validate_v_eng,
    validate_v_len,
    validate_v_link,
    validate_v_misc,
    validate_v_price,
    validate_v_repeat,
    validate_v_sens,
    validate_v_urge,
)
from app.safety.warmup import WarmupTier, get_warmup_tier

__all__ = [
    "GovernorDecision",
    "GuardDecision",
    "PublishGuard",
    "SimilarityCheckResult",
    "ValidationResult",
    "ValidatorReport",
    "WarmupTier",
    "apply_jitter",
    "calculate_similarity",
    "check_content_similarity",
    "check_draft_similarity_in_db",
    "check_governor_limits",
    "check_minimal_guard",
    "compute_normalized_hash",
    "ensure_kill_switch_initialized",
    "get_kill_switch_status",
    "get_target_day_bounds_utc",
    "get_warmup_tier",
    "is_kill_switch_active",
    "is_within_active_hours",
    "normalize_text",
    "set_kill_switch",
    "validate_content",
    "validate_v_claim",
    "validate_v_disc",
    "validate_v_eng",
    "validate_v_len",
    "validate_v_link",
    "validate_v_misc",
    "validate_v_price",
    "validate_v_repeat",
    "validate_v_sens",
    "validate_v_urge",
]
