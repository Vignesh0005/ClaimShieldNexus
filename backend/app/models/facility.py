from sqlalchemy import Float, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedMixin, TenantMixin, UUIDMixin


class Facility(UUIDMixin, TenantMixin, CreatedMixin, Base):
    __tablename__ = "facilities"
    __table_args__ = (UniqueConstraint("tenant_id", "facility_id"),)

    facility_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
