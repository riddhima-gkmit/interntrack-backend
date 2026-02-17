"""User role enum. Used for RBAC: INTERN, MENTOR (tenant), TENANT_ADMIN (tenant), SUPER_ADMIN (platform)."""

from enum import StrEnum

class UserRole(StrEnum):
    """Role of a user; determines permissions and data scope (own, tenant, or platform)."""

    INTERN = "intern"
    MENTOR = "mentor"
    TENANT_ADMIN = "tenant_admin"
    SUPER_ADMIN = "super_admin"
