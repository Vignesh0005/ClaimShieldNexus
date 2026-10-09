from datetime import date

from sqlalchemy import Boolean, Date, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedMixin, TenantMixin, UUIDMixin


class Member(UUIDMixin, TenantMixin, CreatedMixin, Base):
    __tablename__ = "members"
    __table_args__ = (UniqueConstraint("tenant_id", "member_id"),)

    member_id: Mapped[str] = mapped_column(String(100), nullable=False)
    age: Mapped[int | None] = mapped_column(Integer)
    postal_code: Mapped[str | None] = mapped_column(String(20))
    low_income_area: Mapped[bool] = mapped_column(Boolean, default=False)
    plan_type: Mapped[str | None] = mapped_column(String(50))
    policy_start_date: Mapped[date | None] = mapped_column(Date)
    eligibility_end: Mapped[date | None] = mapped_column(Date)
