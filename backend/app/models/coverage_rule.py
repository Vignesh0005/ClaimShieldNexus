from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedMixin, JSONType, UUIDMixin


class CoverageRule(UUIDMixin, CreatedMixin, Base):
    """Coverage rules are shared reference data, not tenant-owned."""

    __tablename__ = "coverage_rules"

    rule_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source_section: Mapped[str | None] = mapped_column(String(100))
    source_document: Mapped[str | None] = mapped_column(String(255))
    check: Mapped[str] = mapped_column(String(100), nullable=False)  # evaluator name in the registry
    inputs: Mapped[list | None] = mapped_column(JSONType)
    valid_values: Mapped[list | None] = mapped_column(JSONType)
    conditions: Mapped[dict | None] = mapped_column(JSONType)
    on_pass: Mapped[str | None] = mapped_column(String(100))
    on_fail: Mapped[str | None] = mapped_column(String(100))
    on_uncertain: Mapped[str | None] = mapped_column(String(100))
    not_fraud: Mapped[bool] = mapped_column(Boolean, default=True)
    not_denial: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Provenance. A rule is authoritative only when it was transcribed from the source document
    # and that transcription has been reviewed; everything else is illustrative.
    authoritative: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    needs_compliance_review: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    disclaimer: Mapped[str | None] = mapped_column(Text)
