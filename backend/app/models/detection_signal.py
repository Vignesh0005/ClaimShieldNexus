import uuid

from sqlalchemy import Float, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedMixin, JSONType, TenantMixin, UUIDMixin


class DetectionSignal(UUIDMixin, TenantMixin, CreatedMixin, Base):
    """One finding from one detector for one claim. Also referred to as a flag in the API."""

    __tablename__ = "detection_signals"

    claim_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("claims.id", ondelete="CASCADE"), index=True, nullable=False)
    signal_id: Mapped[str] = mapped_column(String(100), nullable=False)
    detector: Mapped[str] = mapped_column(String(20), index=True, nullable=False)  # rule | ml | graph | temporal
    rule_name: Mapped[str | None] = mapped_column(String(100))
    model_name: Mapped[str | None] = mapped_column(String(100))
    pattern_name: Mapped[str | None] = mapped_column(String(100))
    confidence: Mapped[float | None] = mapped_column(Float)
    score: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[str | None] = mapped_column(String(20))
    evidence: Mapped[dict] = mapped_column(JSONType, default=dict)
    source_fields: Mapped[list] = mapped_column(JSONType, default=list)
