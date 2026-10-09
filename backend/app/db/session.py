import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, with_loader_criteria
from sqlalchemy.pool import NullPool, StaticPool

from app.config import get_settings
from app.db.base import Base, TenantMixin
from app.integrations.webhooks import WebhookSession

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def make_engine(url: str | None = None, *, null_pool: bool = False) -> AsyncEngine:
    url = url or get_settings().database_url
    kwargs: dict = {}
    if url.startswith("sqlite"):
        if ":memory:" in url:
            kwargs.update(poolclass=StaticPool, connect_args={"check_same_thread": False})
    elif null_pool:
        kwargs.update(poolclass=NullPool)
    else:
        kwargs.update(pool_size=10, max_overflow=20, pool_pre_ping=True)
    return create_async_engine(url, **kwargs)


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        _engine = make_engine()
        _sessionmaker = async_sessionmaker(_engine, class_=WebhookSession, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def create_all() -> None:
    import app.models  # noqa: F401  (registers every table on Base.metadata)

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if conn.dialect.name == "sqlite":
            await conn.run_sync(_add_missing_columns)


def _add_missing_columns(conn) -> None:
    """Development convenience for SQLite only: create_all does not alter existing tables, so
    columns added to a model since the file was created are added here. PostgreSQL uses Alembic."""
    from sqlalchemy import inspect, text
    from sqlalchemy.schema import CreateColumn

    inspector = inspect(conn)
    for table in Base.metadata.sorted_tables:
        existing = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name not in existing:
                ddl = str(CreateColumn(column).compile(dialect=conn.dialect))
                conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {ddl}"))


def bind_tenant(session: AsyncSession, tenant_id: uuid.UUID | None) -> None:
    """Scope a session to one tenant. Passing None lifts the scope (platform-level work only)."""
    session.info["tenant_id"] = tenant_id


@event.listens_for(Session, "do_orm_execute")
def _tenant_filter(state) -> None:
    # Defence in depth: services filter by tenant explicitly, and this adds the same predicate to
    # every ORM SELECT (including relationship loads) on a tenant-bound session.
    tenant_id = state.session.info.get("tenant_id")
    if tenant_id is None or not state.is_select:
        return
    state.statement = state.statement.options(
        with_loader_criteria(TenantMixin, lambda cls: cls.tenant_id == tenant_id, include_aliases=True)
    )


@asynccontextmanager
async def session_scope(tenant_id: uuid.UUID | None = None) -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        bind_tenant(session, tenant_id)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. The tenant is bound later, once the caller has been authenticated."""
    async with get_sessionmaker()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
