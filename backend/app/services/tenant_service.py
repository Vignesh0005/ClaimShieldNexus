import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import Conflict, NotFound, TenantNotFound
from app.core.security import Role, generate_api_key, hash_api_key
from app.models import Tenant, User
from app.utils.validators import slugify

DEFAULT_CONFIG = {
    "thresholds": {"critical": 0.8, "high": 0.6, "medium": 0.4, "routing": 0.7},
    "capacity": {"num_investigators": 3, "hours_per_investigator": 20},
    # Tier 1 (risk score >= thresholds.routing) is always on. Tiers 2 and 3 are per-tenant choices.
    "case_opening": {"tier2_enabled": True, "tier2_rule_threshold": 0.90, "tier3_enabled": True},
    "disabled_rules": [],
    "retrain_threshold": 100,
}


async def get(db: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise TenantNotFound("Tenant not found.")
    return tenant


async def get_by_slug(db: AsyncSession, slug: str) -> Tenant:
    tenant = (await db.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one_or_none()
    if tenant is None:
        raise TenantNotFound(f"Tenant '{slug}' not found.")
    return tenant


async def by_api_key(db: AsyncSession, key: str) -> Tenant | None:
    return (await db.execute(select(Tenant).where(Tenant.api_key_hash == hash_api_key(key)))).scalar_one_or_none()


async def create(db: AsyncSession, name: str, slug: str | None = None, is_demo: bool = False, config: dict | None = None) -> tuple[Tenant, str]:
    """Creates a tenant and returns it with its API key. The key is returned once and only its hash is stored."""
    slug = slug or slugify(name)
    if (await db.execute(select(Tenant.id).where(Tenant.slug == slug))).first():
        raise Conflict(f"A tenant with the identifier '{slug}' already exists.")
    key = generate_api_key(slug)
    tenant = Tenant(name=name, slug=slug, is_demo=is_demo, config={**DEFAULT_CONFIG, **(config or {})}, api_key_hash=hash_api_key(key), api_key_last4=key[-4:])
    db.add(tenant)
    await db.flush()
    return tenant, key


async def rotate_api_key(db: AsyncSession, tenant: Tenant) -> str:
    key = generate_api_key(tenant.slug)
    tenant.api_key_hash, tenant.api_key_last4 = hash_api_key(key), key[-4:]
    await db.flush()
    return key


async def get_user(db: AsyncSession, tenant_id: uuid.UUID, external_id: str) -> User | None:
    return (await db.execute(select(User).where(User.tenant_id == tenant_id, User.external_id == external_id))).scalar_one_or_none()


async def require_user(db: AsyncSession, tenant_id: uuid.UUID, external_id: str) -> User:
    user = await get_user(db, tenant_id, external_id)
    if user is None:
        raise NotFound(f"User '{external_id}' not found in this tenant.")
    return user


async def ensure_user(db: AsyncSession, tenant_id: uuid.UUID, external_id: str, role: Role, email: str | None = None, name: str | None = None) -> User:
    """First sign-in creates the user with the role in their token. After that the stored role is
    authoritative, so an admin can change it without waiting for a new token."""
    user = await get_user(db, tenant_id, external_id)
    if user is None:
        user = User(tenant_id=tenant_id, external_id=external_id, role=role.value, email=email, name=name)
        db.add(user)
        await db.flush()
    return user
