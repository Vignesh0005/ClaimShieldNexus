import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Index, Integer, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedMixin, JSONType, TenantMixin, UUIDMixin

Money = Numeric(12, 2, asdecimal=False)


class Claim(UUIDMixin, TenantMixin, CreatedMixin, Base):
    __tablename__ = "claims"
    __table_args__ = (
        UniqueConstraint("tenant_id", "claim_id"),
        Index("idx_claims_risk", "tenant_id", "risk_score"),
        Index("idx_claims_provider_date", "tenant_id", "provider_id", "service_date"),
        Index("idx_claims_member_date", "tenant_id", "member_id", "service_date"),
    )

    claim_id: Mapped[str] = mapped_column(String(100), nullable=False)
    member_id: Mapped[str | None] = mapped_column(String(100))
    provider_id: Mapped[str | None] = mapped_column(String(100))
    facility_id: Mapped[str | None] = mapped_column(String(100))
    referring_provider_id: Mapped[str | None] = mapped_column(String(100))
    service_date: Mapped[date | None] = mapped_column(Date)
    claim_type: Mapped[str | None] = mapped_column(String(50))
    total_billed: Mapped[float | None] = mapped_column(Money)
    total_paid: Mapped[float | None] = mapped_column(Money)
    diagnosis_codes: Mapped[list] = mapped_column(JSONType, default=list)
    plan_type: Mapped[str | None] = mapped_column(String(50))
    policy_start_date: Mapped[date | None] = mapped_column(Date)
    pre_auth_number: Mapped[str | None] = mapped_column(String(100))
    member_age: Mapped[int | None] = mapped_column(Integer)
    # Fields used by coverage rules that have no dedicated column (documents, location, ...).
    attributes: Mapped[dict] = mapped_column(JSONType, default=dict)

    coverage_status: Mapped[str | None] = mapped_column(String(50))
    coverage_details: Mapped[dict | None] = mapped_column(JSONType)
    risk_score: Mapped[float | None] = mapped_column(Float)
    suspicion_score: Mapped[float | None] = mapped_column(Float)
    evidence_strength: Mapped[float | None] = mapped_column(Float)
    member_harm_score: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[str | None] = mapped_column(String(20))
    priority_tier: Mapped[str | None] = mapped_column(String(20))
    two_axis_quadrant: Mapped[str | None] = mapped_column(String(20))
    model_version: Mapped[str | None] = mapped_column(String(50))

    processing_status: Mapped[str] = mapped_column(String(20), default="processing")
    processing_error: Mapped[str | None] = mapped_column(String(500))
    processing_time_ms: Mapped[int | None] = mapped_column(Integer)
    job_id: Mapped[str | None] = mapped_column(String(100))
    case_ref: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lines: Mapped[list["ClaimLineItem"]] = relationship(  # noqa: F821
        back_populates="claim", cascade="all, delete-orphan", lazy="selectin", order_by="ClaimLineItem.line_id"
    )
