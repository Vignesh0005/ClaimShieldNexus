import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedMixin, JSONType, TenantMixin, UUIDMixin, utcnow
from app.models.claim import Money

OPEN_STATUSES = ("pending_review", "in_review", "needs_info")


class Case(UUIDMixin, TenantMixin, CreatedMixin, Base):
    __tablename__ = "cases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "case_id"),
        Index("idx_cases_status", "tenant_id", "status"),
        Index("idx_cases_risk", "tenant_id", "risk_score"),
    )

    case_id: Mapped[str] = mapped_column(String(100), nullable=False)
    primary_claim_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("claims.id"))
    provider_id: Mapped[str | None] = mapped_column(String(100), index=True)
    risk_score: Mapped[float | None] = mapped_column(Float)
    suspicion_score: Mapped[float | None] = mapped_column(Float)
    member_harm_score: Mapped[float | None] = mapped_column(Float)
    evidence_strength: Mapped[float | None] = mapped_column(Float)
    expected_recovery: Mapped[float | None] = mapped_column(Money)
    estimated_hours: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[str | None] = mapped_column(String(20))
    priority_tier: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(50), default="pending_review")
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    claim_count: Mapped[int] = mapped_column(Integer, default=0)
    members_affected: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[dict] = mapped_column(JSONType, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
