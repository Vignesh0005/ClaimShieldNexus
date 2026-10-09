from sqlalchemy import Boolean, Float, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedMixin, TenantMixin, UUIDMixin


class Provider(UUIDMixin, TenantMixin, CreatedMixin, Base):
    __tablename__ = "providers"
    __table_args__ = (UniqueConstraint("tenant_id", "provider_id"),)

    provider_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    specialty: Mapped[str | None] = mapped_column(String(100), index=True)
    address: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    owner_id: Mapped[str | None] = mapped_column(String(100))
    license_status: Mapped[str] = mapped_column(String(30), default="active")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
