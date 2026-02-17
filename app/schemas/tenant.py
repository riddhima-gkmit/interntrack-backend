"""Tenant (organization) schemas: create (SUPER_ADMIN), update (partial), response, and self-registration (unauthenticated or non-MENTOR)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator

from app.utils.validators import password_strength


class TenantCreateSchema(BaseModel):
    """Create tenant (SUPER_ADMIN only). Name uniqueness enforced in DB/service."""

    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Tenant name must be at least 1 character")
        return v.strip()


class TenantUpdateSchema(BaseModel):
    """Update tenant (PATCH): all fields optional. is_active=False disables tenant signups."""

    name: str | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty_if_present(cls, v: str | None) -> str | None:
        if v is not None and (not v or not v.strip()):
            raise ValueError("Tenant name must be at least 1 character")
        return v.strip() if v else v


class TenantResponseSchema(BaseModel):
    """Tenant in API responses. from_attributes=True for serializing SQLAlchemy model; deleted_at set when soft-deleted."""

    id: UUID
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    model_config = {"from_attributes": True}


class TenantRegisterSchema(BaseModel):
    """Tenant self-registration: creates tenant + first user as TENANT_ADMIN. Used by unauthenticated or non-MENTOR users. first_name/last_name optional."""

    name: str
    email: EmailStr
    username: str
    password: str
    confirm_password: str
    first_name: str | None = None
    last_name: str | None = None

    @field_validator("first_name")
    @classmethod
    def first_name_not_empty_if_present(cls, v: str | None) -> str | None:
        if v is not None and (not v or not v.strip()):
            raise ValueError("First name must be at least 1 character")
        return v.strip() if v else v

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Tenant name must be at least 1 character")
        return v.strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return password_strength(v)

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("Passwords do not match")
        return v
