from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedMixin, JSONType, UUIDMixin, utcnow


class Tenant(UUIDMixin, CreatedMixin, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    # SHA-256 of the API key. The key itself is shown once at creation and never stored.
    api_key_hash: Mapped[str | None] = mapped_column(String(255), index=True)
    api_key_last4: Mapped[str | None] = mapped_column(String(4))
    config: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    field_mapping: Mapped[dict | None] = mapped_column(JSONType)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
