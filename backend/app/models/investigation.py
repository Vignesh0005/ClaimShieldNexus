import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONType, TenantMixin, UUIDMixin, utcnow


class CaseDecision(UUIDMixin, TenantMixin, Base):
    """A reviewer's recorded judgement on a case. Decisions are appended, never edited."""

    __tablename__ = "case_decisions"

    decision_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("cases.id", ondelete="CASCADE"), index=True, nullable=False)
    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    final_label: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    line_decisions: Mapped[list] = mapped_column(JSONType, default=list)
    next_action: Mapped[str | None] = mapped_column(String(100))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    decided_by_label: Mapped[str | None] = mapped_column(String(100))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
