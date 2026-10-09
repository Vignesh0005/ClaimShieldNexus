"""Coverage rule provenance and model evaluation

Revision ID: 0002_provenance
Revises: 0001_initial
Create Date: 2026-10-08
"""
import sqlalchemy as sa
from alembic import op

from app.db.base import JSONType

revision = "0002_provenance"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _has(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # 0001 creates tables from the models as they are when it runs, so a fresh database may
    # already have these columns. Add them only where missing.
    if not _has("coverage_rules", "authoritative"):
        op.add_column("coverage_rules", sa.Column("authoritative", sa.Boolean(), nullable=False, server_default=sa.false()))
    if not _has("coverage_rules", "needs_compliance_review"):
        op.add_column("coverage_rules", sa.Column("needs_compliance_review", sa.Boolean(), nullable=False, server_default=sa.true()))
    if not _has("coverage_rules", "disclaimer"):
        op.add_column("coverage_rules", sa.Column("disclaimer", sa.Text(), nullable=True))
    if not _has("model_versions", "evaluation"):
        op.add_column("model_versions", sa.Column("evaluation", JSONType, nullable=True))


def downgrade() -> None:
    op.drop_column("model_versions", "evaluation")
    for column in ("disclaimer", "needs_compliance_review", "authoritative"):
        op.drop_column("coverage_rules", column)
