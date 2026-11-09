"""app/db/models.py — SQLAlchemy ORM models matching docs/04-DATABASE-SCHEMA.md.

Database: SQLite WAL mode with foreign keys enabled.
All IDs are string UUID4 / ULID.
All timestamps are UTC formatted as ISO-8601 strings.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.clock import utc_now_iso


def generate_uuid() -> str:
    """Generate a random UUID4 string for primary keys."""
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


# ---------------------------------------------------------------------------
# 1. Accounts
# ---------------------------------------------------------------------------
class Account(Base):
    """Threads account entity."""

    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    threads_user_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    country_code: Mapped[str] = mapped_column(String, nullable=False, default="US")
    timezone: Mapped[str] = mapped_column(String, nullable=False, default="America/New_York")
    active_hours_start: Mapped[int] = mapped_column(Integer, nullable=False, default=9)
    active_hours_end: Mapped[int] = mapped_column(Integer, nullable=False, default=21)
    token_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    token_expires_at: Mapped[str | None] = mapped_column(String, nullable=True)
    connected_at: Mapped[str | None] = mapped_column(String, nullable=True)
    warmup_started_at: Mapped[str | None] = mapped_column(String, nullable=True)
    automation_mode: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="manual_approve",
    )
    sample_review_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(
        String, nullable=False, default=utc_now_iso, onupdate=utc_now_iso
    )

    __table_args__ = (
        CheckConstraint(
            "automation_mode IN ('manual_approve','auto_sampled','full_auto')",
            name="ck_accounts_automation_mode",
        ),
    )

    # Relationships
    personas: Mapped[list[Persona]] = relationship("Persona", back_populates="account")
    drafts: Mapped[list[Draft]] = relationship("Draft", back_populates="account")
    posts: Mapped[list[Post]] = relationship("Post", back_populates="account")
    snapshots: Mapped[list[AccountSnapshot]] = relationship("AccountSnapshot", back_populates="account")


# ---------------------------------------------------------------------------
# 2. Niches
# ---------------------------------------------------------------------------
class Niche(Base):
    """Product and content niche."""

    __tablename__ = "niches"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array string
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(
        String, nullable=False, default=utc_now_iso, onupdate=utc_now_iso
    )

    __table_args__ = (
        CheckConstraint("status IN ('active','paused','archived')", name="ck_niches_status"),
    )

    # Relationships
    products: Mapped[list[Product]] = relationship("Product", back_populates="niche")
    arms: Mapped[list[ExperimentArm]] = relationship("ExperimentArm", back_populates="niche")
    drafts: Mapped[list[Draft]] = relationship("Draft", back_populates="niche")


# ---------------------------------------------------------------------------
# 3. Products
# ---------------------------------------------------------------------------
class Product(Base):
    """Affiliate product catalog item (no price columns)."""

    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    niche_id: Mapped[str] = mapped_column(String, ForeignKey("niches.id"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    benable_url: Mapped[str] = mapped_column(String, nullable=False)
    amazon_ref_url: Mapped[str | None] = mapped_column(String, nullable=True)
    benefits: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array string
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array string
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    last_used_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(
        String, nullable=False, default=utc_now_iso, onupdate=utc_now_iso
    )

    __table_args__ = (
        CheckConstraint("status IN ('active','paused','archived')", name="ck_products_status"),
        Index("ix_products_niche", "niche_id", "status"),
    )

    # Relationships
    niche: Mapped[Niche] = relationship("Niche", back_populates="products")
    drafts: Mapped[list[Draft]] = relationship("Draft", back_populates="product")
    clicks: Mapped[list[LinkClick]] = relationship("LinkClick", back_populates="product")


# ---------------------------------------------------------------------------
# 4. Styles
# ---------------------------------------------------------------------------
class Style(Base):
    """Content style profiles."""

    __tablename__ = "styles"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    tone_rules: Mapped[str] = mapped_column(Text, nullable=False)
    max_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=400)
    good_examples: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array string
    bad_examples: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array string
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(
        String, nullable=False, default=utc_now_iso, onupdate=utc_now_iso
    )

    # Relationships
    arms: Mapped[list[ExperimentArm]] = relationship("ExperimentArm", back_populates="style")
    drafts: Mapped[list[Draft]] = relationship("Draft", back_populates="style")


# ---------------------------------------------------------------------------
# 5. Personas
# ---------------------------------------------------------------------------
class Persona(Base):
    """Account persona definition and affiliate disclosure rule."""

    __tablename__ = "personas"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    account_id: Mapped[str] = mapped_column(String, ForeignKey("accounts.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    voice: Mapped[str] = mapped_column(Text, nullable=False)
    avoid: Mapped[str | None] = mapped_column(Text, nullable=True)
    disclosure_text: Mapped[str] = mapped_column(
        String, nullable=False, default="Affiliate link"
    )
    disclosure_position: Mapped[str] = mapped_column(
        String, nullable=False, default="end"
    )
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(
        String, nullable=False, default=utc_now_iso, onupdate=utc_now_iso
    )

    __table_args__ = (
        CheckConstraint(
            "disclosure_position IN ('start','end')",
            name="ck_personas_disclosure_position",
        ),
    )

    # Relationships
    account: Mapped[Account] = relationship("Account", back_populates="personas")


# ---------------------------------------------------------------------------
# 6. Experiments
# ---------------------------------------------------------------------------
class Experiment(Base):
    """A/B and structured testing experiments."""

    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    phase: Mapped[str] = mapped_column(String, nullable=False)
    start_date: Mapped[str] = mapped_column(String, nullable=False)
    end_date: Mapped[str | None] = mapped_column(String, nullable=True)
    config: Mapped[str] = mapped_column(Text, nullable=False)  # JSON config
    status: Mapped[str] = mapped_column(String, nullable=False, default="planned")
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(
        String, nullable=False, default=utc_now_iso, onupdate=utc_now_iso
    )

    __table_args__ = (
        CheckConstraint(
            "phase IN ('niche_test','style_test','scale')",
            name="ck_experiments_phase",
        ),
        CheckConstraint(
            "status IN ('planned','running','completed','aborted')",
            name="ck_experiments_status",
        ),
    )

    # Relationships
    arms: Mapped[list[ExperimentArm]] = relationship("ExperimentArm", back_populates="experiment")


# ---------------------------------------------------------------------------
# 7. Experiment Arms
# ---------------------------------------------------------------------------
class ExperimentArm(Base):
    """Individual arm in an experiment."""

    __tablename__ = "experiment_arms"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    experiment_id: Mapped[str] = mapped_column(
        String, ForeignKey("experiments.id"), nullable=False
    )
    niche_id: Mapped[str | None] = mapped_column(String, ForeignKey("niches.id"), nullable=True)
    style_id: Mapped[str | None] = mapped_column(String, ForeignKey("styles.id"), nullable=True)
    target_posts: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)

    # Relationships
    experiment: Mapped[Experiment] = relationship("Experiment", back_populates="arms")
    niche: Mapped[Niche | None] = relationship("Niche", back_populates="arms")
    style: Mapped[Style | None] = relationship("Style", back_populates="arms")
    drafts: Mapped[list[Draft]] = relationship("Draft", back_populates="arm")


# ---------------------------------------------------------------------------
# 8. Drafts
# ---------------------------------------------------------------------------
class Draft(Base):
    """Draft posts generated by AI awaiting review, scheduled, or published."""

    __tablename__ = "drafts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    account_id: Mapped[str] = mapped_column(String, ForeignKey("accounts.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False, default="post")
    arm_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("experiment_arms.id"), nullable=True
    )
    niche_id: Mapped[str | None] = mapped_column(String, ForeignKey("niches.id"), nullable=True)
    style_id: Mapped[str | None] = mapped_column(String, ForeignKey("styles.id"), nullable=True)
    product_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("products.id"), nullable=True
    )
    prompt_version: Mapped[str] = mapped_column(String, nullable=False)
    llm_model: Mapped[str] = mapped_column(String, nullable=False)
    parts: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array string
    llm_raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    link_url: Mapped[str | None] = mapped_column(String, nullable=True)
    link_placement: Mapped[str | None] = mapped_column(String, nullable=True)
    target_post_url: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    validator_report: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    text_hash: Mapped[str] = mapped_column(String, nullable=False)
    scheduled_at: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    expires_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(
        String, nullable=False, default=utc_now_iso, onupdate=utc_now_iso
    )

    __table_args__ = (
        CheckConstraint("kind IN ('post','thread','comment')", name="ck_drafts_kind"),
        CheckConstraint(
            "link_placement IN ('in_post','in_first_reply','none') OR link_placement IS NULL",
            name="ck_drafts_link_placement",
        ),
        CheckConstraint(
            "status IN ('generated','rejected_auto','pending_review','approved','rejected',"
            "'scheduled','publishing','published','failed','failed_permanent','expired','cancelled')",
            name="ck_drafts_status",
        ),
        Index("ix_drafts_status", "status", "scheduled_at"),
        Index("ix_drafts_hash", "text_hash"),
    )

    # Relationships
    account: Mapped[Account] = relationship("Account", back_populates="drafts")
    arm: Mapped[ExperimentArm | None] = relationship("ExperimentArm", back_populates="drafts")
    niche: Mapped[Niche | None] = relationship("Niche", back_populates="drafts")
    style: Mapped[Style | None] = relationship("Style", back_populates="drafts")
    product: Mapped[Product | None] = relationship("Product", back_populates="drafts")
    post: Mapped[Post | None] = relationship("Post", back_populates="draft", uselist=False)


# ---------------------------------------------------------------------------
# 9. Posts
# ---------------------------------------------------------------------------
class Post(Base):
    """Published posts on Threads. draft_id is UNIQUE for idempotency."""

    __tablename__ = "posts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    draft_id: Mapped[str] = mapped_column(
        String, ForeignKey("drafts.id"), unique=True, nullable=False
    )
    account_id: Mapped[str] = mapped_column(String, ForeignKey("accounts.id"), nullable=False)
    threads_media_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    permalink: Mapped[str | None] = mapped_column(String, nullable=True)
    creation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    published_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)

    # Relationships
    draft: Mapped[Draft] = relationship("Draft", back_populates="post")
    account: Mapped[Account] = relationship("Account", back_populates="posts")
    metrics: Mapped[list[PostMetric]] = relationship("PostMetric", back_populates="post")
    clicks: Mapped[list[LinkClick]] = relationship("LinkClick", back_populates="post")


# ---------------------------------------------------------------------------
# 10. Post Metrics
# ---------------------------------------------------------------------------
class PostMetric(Base):
    """Time-bucketed insights for published posts."""

    __tablename__ = "post_metrics"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    post_id: Mapped[str] = mapped_column(String, ForeignKey("posts.id"), nullable=False)
    captured_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)
    age_bucket: Mapped[str] = mapped_column(String, nullable=False)
    views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    likes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    replies: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reposts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quotes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "age_bucket IN ('1h','24h','72h','7d')",
            name="ck_post_metrics_age_bucket",
        ),
        UniqueConstraint("post_id", "age_bucket", name="uq_post_metrics_post_age"),
    )

    # Relationships
    post: Mapped[Post] = relationship("Post", back_populates="metrics")


# ---------------------------------------------------------------------------
# 11. Link Clicks
# ---------------------------------------------------------------------------
class LinkClick(Base):
    """Manual or CSV-imported Benable clicks."""

    __tablename__ = "link_clicks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    product_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("products.id"), nullable=True
    )
    post_id: Mapped[str | None] = mapped_column(String, ForeignKey("posts.id"), nullable=True)
    period_start: Mapped[str] = mapped_column(String, nullable=False)
    period_end: Mapped[str] = mapped_column(String, nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False, default="benable_manual")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)

    # Relationships
    product: Mapped[Product | None] = relationship("Product", back_populates="clicks")
    post: Mapped[Post | None] = relationship("Post", back_populates="clicks")


# ---------------------------------------------------------------------------
# 12. Account Snapshots
# ---------------------------------------------------------------------------
class AccountSnapshot(Base):
    """Account growth tracking."""

    __tablename__ = "account_snapshots"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    account_id: Mapped[str] = mapped_column(String, ForeignKey("accounts.id"), nullable=False)
    captured_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)
    followers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_views: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    account: Mapped[Account] = relationship("Account", back_populates="snapshots")


# ---------------------------------------------------------------------------
# 13. System State
# ---------------------------------------------------------------------------
class SystemState(Base):
    """Key-value system state flags (e.g. kill_switch, kill_reason)."""

    __tablename__ = "system_state"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(
        String, nullable=False, default=utc_now_iso, onupdate=utc_now_iso
    )


# ---------------------------------------------------------------------------
# 14. Settings
# ---------------------------------------------------------------------------
class Setting(Base):
    """System configuration parameters (JSON payload)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    updated_at: Mapped[str] = mapped_column(
        String, nullable=False, default=utc_now_iso, onupdate=utc_now_iso
    )


# ---------------------------------------------------------------------------
# 15. Incidents
# ---------------------------------------------------------------------------
class Incident(Base):
    """System incident tracking."""

    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)

    __table_args__ = (
        CheckConstraint(
            "severity IN ('info','warning','critical')",
            name="ck_incidents_severity",
        ),
    )


# ---------------------------------------------------------------------------
# 16. Audit Log
# ---------------------------------------------------------------------------
class AuditLog(Base):
    """Append-only audit trail."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    entity: Mapped[str | None] = mapped_column(String, nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string without secrets


# ---------------------------------------------------------------------------
# 17. Job Locks
# ---------------------------------------------------------------------------
class JobLock(Base):
    """Distributed lock mechanism for background worker jobs."""

    __tablename__ = "job_locks"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    locked_until: Mapped[str] = mapped_column(String, nullable=False)
    owner: Mapped[str] = mapped_column(String, nullable=False)


# ---------------------------------------------------------------------------
# 18. LLM Usage
# ---------------------------------------------------------------------------
class LlmUsage(Base):
    """Daily LLM call counter to enforce safety budget."""

    __tablename__ = "llm_usage"

    day: Mapped[str] = mapped_column(String, primary_key=True)  # YYYY-MM-DD
    model: Mapped[str] = mapped_column(String, primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
