import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import Schema


class TenantCreate(Schema):
    name: str = Field(min_length=2, max_length=255)
    slug: str | None = Field(default=None, max_length=60, pattern=r"^[a-z0-9-]+$")
    is_demo: bool = False
    config: dict = Field(default_factory=dict)


class TenantOut(Schema):
    id: uuid.UUID
    name: str
    slug: str
    active: bool
    is_demo: bool
    api_key_last4: str | None
    created_at: datetime


class FieldMappingIn(Schema):
    # {"their_field": "claimshield_field"}
    mapping: dict[str, str] = Field(min_length=1, max_length=200)


class ConfigIn(Schema):
    config: dict


class UserCreate(Schema):
    external_id: str = Field(min_length=1, max_length=100)
    email: str | None = None
    name: str | None = None
    role: Literal["admin", "siu_investigator", "analyst", "viewer"] = "viewer"


class UserUpdate(Schema):
    role: Literal["admin", "siu_investigator", "analyst", "viewer"] | None = None
    active: bool | None = None


class UserOut(Schema):
    id: uuid.UUID
    external_id: str
    email: str | None
    name: str | None
    role: str
    active: bool


class DevTokenIn(Schema):
    tenant: str  # slug
    user: str  # external id
    role: Literal["admin", "siu_investigator", "analyst", "viewer"] = "siu_investigator"
    platform_admin: bool = False
