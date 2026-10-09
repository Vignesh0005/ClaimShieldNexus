import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONType, TenantMixin, UUIDMixin, utcnow


class Brief(UUIDMixin, TenantMixin, Base):
    __tablename__ = "briefs"

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("cases.id", ondelete="CASCADE"), index=True, nullable=False)
    brief_type: Mapped[str] = mapped_column(String(20), nullable=False)  # technical | plain
    content: Mapped[dict] = mapped_column(JSONType, default=dict)
    content_markdown: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(String(50))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Counterfactual(UUIDMixin, TenantMixin, Base):
    __tablename__ = "counterfactuals"

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("cases.id", ondelete="CASCADE"), index=True, nullable=False)
    scenario: Mapped[str] = mapped_column(Text, nullable=False)
    original_risk: Mapped[float | None] = mapped_column(Float)
    counterfactual_risk: Mapped[float | None] = mapped_column(Float)
    conditions: Mapped[dict] = mapped_column(JSONType, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
