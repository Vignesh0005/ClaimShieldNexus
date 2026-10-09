from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Tenant, User
from app.services import tenant_service

DEMO_USERS = [
    ("ADM-002", "R. Alvarez", "admin"),
    ("AUD-007", "A. Sharma", "siu_investigator"),
    ("AUD-011", "J. Okafor", "siu_investigator"),
    ("AUD-004", "L. Chen", "siu_investigator"),
    ("ANL-014", "M. Petrov", "analyst"),
    ("VWR-021", "S. Doyle", "viewer"),
]


async def seed_tenant(db: AsyncSession, name: str, slug: str, is_demo: bool = True) -> tuple[Tenant, str | None]:
    """Creates the tenant and its demo users if absent. Returns the API key only when the tenant
    was created in this call, because the key cannot be recovered afterwards."""
    tenant = (await db.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one_or_none()
    api_key = None
    if tenant is None:
        tenant, api_key = await tenant_service.create(db, name, slug, is_demo=is_demo)
    for external_id, user_name, role in DEMO_USERS:
        if await tenant_service.get_user(db, tenant.id, external_id) is None:
            db.add(User(tenant_id=tenant.id, external_id=external_id, name=user_name, role=role, email=f"{external_id.lower()}@{slug}.example"))
    await db.flush()
    return tenant, api_key
