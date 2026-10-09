import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedMixin, JSONType, TenantMixin, UUIDMixin
from app.models.claim import Money


class ClaimLineItem(UUIDMixin, TenantMixin, CreatedMixin, Base):
    __tablename__ = "claim_line_items"

    claim_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("claims.id", ondelete="CASCADE"), index=True, nullable=False)
    line_id: Mapped[str] = mapped_column(String(100), nullable=False)
    cpt_code: Mapped[str | None] = mapped_column(String(20), index=True)
    modifiers: Mapped[list] = mapped_column(JSONType, default=list)
    units: Mapped[int | None] = mapped_column(Integer)
    billed_amount: Mapped[float | None] = mapped_column(Money)
    paid_amount: Mapped[float | None] = mapped_column(Money)
    service_date: Mapped[date | None] = mapped_column(Date)
    diagnosis_pointer: Mapped[list] = mapped_column(JSONType, default=list)

    claim: Mapped["Claim"] = relationship(back_populates="lines")  # noqa: F821
