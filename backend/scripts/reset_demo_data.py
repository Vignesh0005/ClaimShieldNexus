"""Clear local synthetic demo records while preserving accounts and integration configuration."""
import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from app.config import get_settings
from app.db.base import Base
import app.models  # noqa: F401

KEEP = {"tenants", "users", "coverage_rules", "model_versions"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Back up and clear demo records; otherwise preview counts")
    args = parser.parse_args()
    settings = get_settings()
    url = make_url(settings.database_url)
    if settings.is_production or url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise RuntimeError("This reset supports only a local, non-production SQLite demo database.")
    database = Path(url.database).resolve()
    if not database.is_file():
        raise RuntimeError("Database not found.")
    with sqlite3.connect(database, timeout=30) as conn:
        ids = [r[0] for r in conn.execute("SELECT id FROM tenants WHERE is_demo = 1")]
        tables = [t for t in reversed(Base.metadata.sorted_tables) if t.name not in KEEP and "tenant_id" in t.c]
        existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = ?", ("table",))}
        tables = [t for t in tables if t.name in existing]
        if not ids:
            print("No demo tenants found; nothing changed.")
            return
        slots = ",".join("?" for _ in ids)
        counts = {t.name: conn.execute(f'SELECT COUNT(*) FROM "{t.name}" WHERE tenant_id IN ({slots})', ids).fetchone()[0] for t in tables}
        print("Demo records:", counts)
        if not args.apply:
            print("Preview only. Use --apply to back up and clear these demo records.")
            return
        backup_dir = database.parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        backup = backup_dir / f"claimshield-before-reset-{datetime.now():%Y%m%d-%H%M%S}.db"
        with sqlite3.connect(backup) as target:
            conn.backup(target)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN IMMEDIATE")
        try:
            for table in tables:
                conn.execute(f'DELETE FROM "{table.name}" WHERE tenant_id IN ({slots})', ids)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        remaining = {t.name: conn.execute(f'SELECT COUNT(*) FROM "{t.name}" WHERE tenant_id IN ({slots})', ids).fetchone()[0] for t in tables}
        print("Remaining demo records:", remaining)
        if any(remaining.values()):
            raise RuntimeError("Some demo records remain.")
        print("Backup:", backup)
        print("Preserved tenant settings, webhook registrations, users, coverage rules and trained models.")


if __name__ == "__main__":
    main()
