"""User schemas: response (with tenant_id), create, update, me-update, change-password. Used by user routes and invitation accept flow."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator

from app.enums import UserRole
from app.utils.validators import first_name_not_empty, password_strength


class UserResponseSchema(BaseModel):
    """User in API responses. Never include hashed_password. tenant_id is None for SUPER_ADMIN; from_attributes for ORM."""

    id: UUID
    tenant_id: UUID | None = None  # None when user.tenant_id is None (SUPER_ADMIN).
    username: str
    email: str
    first_name: str
    last_name: str
    role: UserRole
    is_verified: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None  # Set when soft-deleted.

    model_config = {"from_attributes": True}


class UserMeUpdateSchema(BaseModel):
    """Update own profile (PATCH /me/). Only first_name and last_name; email/username/role not editable here."""

    first_name: str | None = None
    last_name: str | None = None

    @field_validator("first_name")
    @classmethod
    def first_name_not_empty_if_present(cls, v: str | None) -> str | None:
        if v is not None and (not v or not v.strip()):
            raise ValueError("First name must be at least 1 character")
        return v.strip() if v else v


class ChangePasswordSchema(BaseModel):
    """Change own password. Service verifies old_password before applying new; same strength and match validators as register."""

    old_password: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return password_strength(v)

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Passwords do not match")
        return v


class UserCreateSchema(BaseModel):
    """Create user (TENANT_ADMIN: tenant from JWT; SUPER_ADMIN: pass tenant via X-Tenant-ID header)."""

    username: str
    email: EmailStr
    first_name: str
    last_name: str
    password: str
    confirm_password: str
    role: UserRole

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, v: str) -> str:
        return first_name_not_empty(v)

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, v):
        """Accept role in any casing (e.g. intern, INTERN) before enum validation."""
        if isinstance(v, str):
            return v.strip().lower()
        return v

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


class UserUpdateSchema(BaseModel):
    """Update user (PATCH by admin). All fields optional. is_active to enable/disable user; role/email/username not in schema."""

    first_name: str | None = None
    last_name: str | None = None
    is_active: bool | None = None  # Admin can activate/deactivate user.

    @field_validator("first_name")
    @classmethod
    def first_name_not_empty_if_present(cls, v: str | None) -> str | None:
        if v is not None and (not v or not v.strip()):
            raise ValueError("First name must be at least 1 character")
        return v.strip() if v else v
