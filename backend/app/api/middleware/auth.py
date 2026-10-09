import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.exceptions import Forbidden, Unauthorized
from app.core.security import Principal, Role, decode_token, parse_role
from app.models import Tenant
from app.services import tenant_service


async def _tenant_from_claim(db: AsyncSession, value: str | None) -> Tenant:
    if not value:
        raise Unauthorized("The access token does not name a tenant.")
    try:
        tenant = await db.get(Tenant, uuid.UUID(str(value)))
    except ValueError:
        tenant = None
    if tenant is None:
        try:
            tenant = await tenant_service.get_by_slug(db, str(value))
        except Exception as exc:  # noqa: BLE001
            raise Unauthorized("The access token names an unknown tenant.") from exc
    return tenant


async def authenticate(request: Request, db: AsyncSession) -> tuple[Principal, Tenant]:
    """Resolves the caller from `X-API-Key` (machine ingest) or `Authorization: Bearer` (users).
    Runs before the session is bound to a tenant, since the tenant is what it discovers."""
    api_key = request.headers.get("x-api-key")
    authorization = request.headers.get("authorization", "")

    if api_key:
        tenant = await tenant_service.by_api_key(db, api_key)
        if tenant is None:
            raise Unauthorized("The API key is not valid.")
        principal = Principal(tenant_id=tenant.id, role=Role.API, subject="api-key", actor_type="api")
    elif authorization.lower().startswith("bearer "):
        claims = decode_token(authorization[7:].strip())
        tenant = await _tenant_from_claim(db, claims.get("tenant_id"))
        subject = str(claims.get("sub") or "")
        if not subject:
            raise Unauthorized("The access token has no subject.")
        platform_admin = bool(claims.get("platform_admin", False))

        # A platform administrator may act inside another tenant by naming it explicitly. Anyone
        # else naming a tenant other than their own is refused rather than silently ignored.
        requested = request.headers.get("x-tenant-id")
        if requested and requested not in (tenant.slug, str(tenant.id)):
            if not platform_admin:
                raise Forbidden("You do not have access to that tenant.")
            tenant = await _tenant_from_claim(db, requested)

        user = await tenant_service.ensure_user(db, tenant.id, subject, parse_role(claims.get("role")), claims.get("email"), claims.get("name"))
        await db.commit()
        if not user.active:
            raise Forbidden("This user account has been deactivated.")
        principal = Principal(tenant_id=tenant.id, role=parse_role(user.role), subject=subject, user_id=user.id, platform_admin=platform_admin, claims=claims)
    else:
        raise Unauthorized("Send an API key in X-API-Key or a bearer token in Authorization.")

    if not tenant.active:
        raise Forbidden("This tenant is inactive.")
    return principal, tenant
