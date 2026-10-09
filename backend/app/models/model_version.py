from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedMixin, JSONType, UUIDMixin


class ModelVersion(UUIDMixin, CreatedMixin, Base):
    __tablename__ = "model_versions"

    version: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    model_type: Mapped[str | None] = mapped_column(String(50))
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    training_samples: Mapped[int | None] = mapped_column(Integer)
    precision: Mapped[float | None] = mapped_column(Float)
    recall: Mapped[float | None] = mapped_column(Float)
    f1: Mapped[float | None] = mapped_column(Float)
    roc_auc: Mapped[float | None] = mapped_column(Float)
    pr_auc: Mapped[float | None] = mapped_column(Float)
    false_positive_rate: Mapped[float | None] = mapped_column(Float)
    false_negative_rate: Mapped[float | None] = mapped_column(Float)
    confusion_matrix: Mapped[dict | None] = mapped_column(JSONType)
    hyperparameters: Mapped[dict | None] = mapped_column(JSONType)
    feature_importance: Mapped[dict | None] = mapped_column(JSONType)
    evaluation: Mapped[dict | None] = mapped_column(JSONType)  # random-split and provider-split metrics
    artifact_path: Mapped[str | None] = mapped_column(String(255))
    is_deployed: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
