"""app/safety — System safety, guard, rate governor, validators, similarity, and kill switch."""

from app.safety.killswitch import (
    ensure_kill_switch_initialized,
    get_kill_switch_status,
    is_kill_switch_active,
    set_kill_switch,
)
from app.safety.minimal_guard import GuardDecision, check_minimal_guard
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

__all__ = [
    "GuardDecision",
    "SimilarityCheckResult",
    "ValidationResult",
    "ValidatorReport",
    "calculate_similarity",
    "check_content_similarity",
    "check_draft_similarity_in_db",
    "check_minimal_guard",
    "compute_normalized_hash",
    "ensure_kill_switch_initialized",
    "get_kill_switch_status",
    "is_kill_switch_active",
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
