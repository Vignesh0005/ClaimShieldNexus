import uuid
from contextvars import ContextVar

# Set once per request (or per worker task) after authentication. Used by logging and the audit
# logger; database scoping uses the session-bound tenant in db/session.py.
_current_tenant: ContextVar[uuid.UUID | None] = ContextVar("current_tenant", default=None)


def set_current_tenant(tenant_id: uuid.UUID | None) -> None:
    _current_tenant.set(tenant_id)


def get_current_tenant() -> uuid.UUID | None:
    return _current_tenant.get()
