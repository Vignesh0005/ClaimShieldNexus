from datetime import date

from sqlalchemy import Date, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedMixin, TenantMixin, UUIDMixin


class Referral(UUIDMixin, TenantMixin, CreatedMixin, Base):
    """One provider referring a member to another. Derived from referring_provider_id on claims."""

    __tablename__ = "referrals"
    __table_args__ = (Index("idx_referrals_pair", "tenant_id", "from_provider_id", "to_provider_id"),)

    from_provider_id: Mapped[str] = mapped_column(String(100), nullable=False)
    to_provider_id: Mapped[str] = mapped_column(String(100), nullable=False)
    member_id: Mapped[str | None] = mapped_column(String(100))
    claim_id: Mapped[str | None] = mapped_column(String(100))
    referral_date: Mapped[date | None] = mapped_column(Date, index=True)
