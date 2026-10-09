import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONType, TenantMixin, UUIDMixin, utcnow


class ModelFeedback(UUIDMixin, TenantMixin, Base):
    __tablename__ = "model_feedback"

    feedback_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    claim_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("claims.id"), nullable=False)
    case_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("cases.id"))
    model_version: Mapped[str | None] = mapped_column(String(50))
    fraud_probability: Mapped[float | None] = mapped_column(Float)
    risk_score: Mapped[float | None] = mapped_column(Float)
    human_decision: Mapped[str | None] = mapped_column(String(50))
    # Reviewer's label used for training: 1 = confirmed for referral, 0 = not confirmed.
    final_label: Mapped[int | None] = mapped_column(Integer, index=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    reviewer_label: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    time_spent_seconds: Mapped[int | None] = mapped_column(Integer)
    features: Mapped[dict | None] = mapped_column(JSONType)  # feature vector at scoring time
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    used_in_training: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    training_batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
