from datetime import date

from sqlalchemy import Date, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedMixin, JSONType, TenantMixin, UUIDMixin
from app.models.claim import Money


class GraphSnapshot(UUIDMixin, TenantMixin, CreatedMixin, Base):
    """Provider-member-facility relationships as of one date, kept for time-travel replay."""

    __tablename__ = "graph_snapshots"
    __table_args__ = (Index("idx_graph_tenant_date", "tenant_id", "snapshot_date"),)

    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    nodes: Mapped[list] = mapped_column(JSONType, default=list)
    edges: Mapped[list] = mapped_column(JSONType, default=list)
    metrics: Mapped[dict] = mapped_column(JSONType, default=dict)


class ProviderForecast(UUIDMixin, TenantMixin, CreatedMixin, Base):
    __tablename__ = "provider_forecasts"
    __table_args__ = (UniqueConstraint("tenant_id", "provider_id", "forecast_date", "horizon_days"),)

    provider_id: Mapped[str] = mapped_column(String(100), nullable=False)
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_probability: Mapped[float | None] = mapped_column(Float)
    predicted_dollars: Mapped[float | None] = mapped_column(Money)
    model_version: Mapped[str | None] = mapped_column(String(50))
