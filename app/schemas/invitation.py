"""Invitation schema: email and role (INTERN or MENTOR) for creating an invite. Used by POST /users/invite/. Tenant and created_by come from JWT/route."""

from pydantic import BaseModel, EmailStr, field_validator

from app.enums import InvitationRole


class InvitationCreateSchema(BaseModel):
    """Create invitation. Email = invitee; role = INTERN or MENTOR (default INTERN). Tenant and created_by from route deps."""

    email: EmailStr
    role: InvitationRole = InvitationRole.INTERN.value  # Default INTERN; MENTOR can invite as INTERN or MENTOR.

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, v):
        """Normalize string to lowercase before enum validation so API accepts any casing (e.g. INTERN, intern)."""
        if isinstance(v, str):
            return v.strip().lower()
        return v
