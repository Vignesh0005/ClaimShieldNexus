"""Initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-08

Creates every table from the models as they stood at this revision, then makes the audit log
append-only at the database level on PostgreSQL. Later schema changes must be written as explicit
`op.` operations (alembic revision --autogenerate) and must not call create_all again.
"""
from alembic import op

import app.models  # noqa: F401
from app.db.base import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

AUDIT_GUARD = """
CREATE OR REPLACE FUNCTION audit_logs_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only';
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Available for embedding columns added in later revisions; harmless if unused.
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind)
    if bind.dialect.name == "postgresql":
        op.execute(AUDIT_GUARD)
        op.execute("CREATE TRIGGER audit_logs_no_update BEFORE UPDATE OR DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION audit_logs_append_only()")
        op.execute("CREATE TRIGGER audit_logs_no_truncate BEFORE TRUNCATE ON audit_logs FOR EACH STATEMENT EXECUTE FUNCTION audit_logs_append_only()")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_logs_no_update ON audit_logs")
        op.execute("DROP TRIGGER IF EXISTS audit_logs_no_truncate ON audit_logs")
        op.execute("DROP FUNCTION IF EXISTS audit_logs_append_only()")
    Base.metadata.drop_all(bind)
