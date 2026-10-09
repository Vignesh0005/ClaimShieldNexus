import hashlib
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

import jwt

from app.config import get_settings
from app.core.exceptions import Forbidden, Unauthorized


class Role(str, Enum):
    ADMIN = "admin"
    SIU_INVESTIGATOR = "siu_investigator"
    ANALYST = "analyst"
    VIEWER = "viewer"
    API = "api"  # machine caller authenticated with a tenant API key


PERMISSIONS: dict[Role, set[str]] = {
    Role.ADMIN: {"*"},
    Role.SIU_INVESTIGATOR: {
        "claims:read", "cases:read", "cases:decide", "cases:assign", "queue:read", "queue:optimize",
        "briefs:read", "briefs:generate", "network:read", "audit:read", "analytics:read",
        "feedback:write", "models:read", "coverage:read", "copilot:use", "detection:run", "inject:run",
    },
    Role.ANALYST: {
        "claims:read", "cases:read", "queue:read", "queue:optimize", "analytics:read", "network:read",
        "briefs:read", "audit:read", "models:read", "coverage:read", "inject:run",
    },
    Role.VIEWER: {"claims:read", "cases:read", "queue:read", "analytics:read", "models:read", "coverage:read"},
    Role.API: {"claims:write", "claims:read", "coverage:read"},
}


@dataclass
class Principal:
    tenant_id: uuid.UUID
    role: Role
    subject: str  # external user id, or "api-key"
    user_id: uuid.UUID | None = None
    actor_type: str = "user"
    platform_admin: bool = False
    claims: dict = field(default_factory=dict)

    def can(self, permission: str) -> bool:
        granted = PERMISSIONS.get(self.role, set())
        return "*" in granted or permission in granted

    def require(self, permission: str) -> None:
        if not self.can(permission):
            raise Forbidden(f"Role '{self.role.value}' does not have permission '{permission}'.")


# ---------- API keys ----------

def generate_api_key(tenant_slug: str) -> str:
    return f"csn_{tenant_slug}_{secrets.token_urlsafe(32)}"


def hash_api_key(key: str) -> str:
    # Keys are 256 bits of randomness, so a fast hash is appropriate (no password stretching needed).
    return hashlib.sha256(key.encode()).hexdigest()


# ---------- JWT ----------

def create_access_token(
    *, subject: str, tenant_id: uuid.UUID | str, role: Role | str, platform_admin: bool = False, minutes: int = 480
) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "tenant_id": str(tenant_id),
        "role": Role(role).value,
        "platform_admin": platform_admin,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


_jwks_client: jwt.PyJWKClient | None = None


def decode_token(token: str) -> dict:
    """Verifies a bearer token. Clerk tokens (RS256, JWKS) when configured, otherwise HS256."""
    global _jwks_client
    settings = get_settings()
    try:
        if settings.clerk_jwks_url:
            if _jwks_client is None:
                _jwks_client = jwt.PyJWKClient(settings.clerk_jwks_url)
            key = _jwks_client.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], issuer=settings.clerk_issuer, options={"verify_aud": False})
            meta = claims.get("public_metadata") or claims.get("metadata") or {}
            claims.setdefault("tenant_id", meta.get("tenant_id") or claims.get("org_id"))
            claims.setdefault("role", meta.get("role", Role.VIEWER.value))
            claims.setdefault("platform_admin", bool(meta.get("platform_admin", False)))
            return claims
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise Unauthorized("The access token has expired. Sign in again.") from exc
    except jwt.PyJWTError as exc:
        raise Unauthorized("The access token is not valid.") from exc


def parse_role(value: str | None) -> Role:
    try:
        role = Role(value or Role.VIEWER.value)
    except ValueError:
        return Role.VIEWER  # unknown roles get the least privilege
    return Role.VIEWER if role is Role.API else role
