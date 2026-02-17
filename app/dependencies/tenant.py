"""Tenant context: load current user's tenant and enforce tenant-scoped access."""

from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import tenant_crud
from app.database.init_db import get_db
from app.dependencies.user import get_current_user
from app.enums import UserRole
from app.models import Tenant, User


async def get_current_tenant(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """Load current user's tenant; require user to have a tenant_id (not SUPER_ADMIN without context)."""
    # SUPER_ADMIN has tenant_id=None; tenant-scoped routes should not use this dependency for them.
    if current_user.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have a tenant assigned. This action requires a tenant context.",
        )
    tenant = await tenant_crud.get_tenant(db, current_user.tenant_id)
    if not tenant:
        # Tenant was deleted or missing (data inconsistency).
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    # Inactive tenants cannot be used; blocks access without revealing tenant existence elsewhere.
    if not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This tenant is inactive and cannot be used for this action.",
        )
    return tenant


def verify_tenant_access(current_user: User, tenant_id: UUID) -> None:
    """
    Verify that current user can access the given tenant.
    TENANT_ADMIN: only own tenant (current_user.tenant_id == tenant_id).
    SUPER_ADMIN: any tenant.
    Raises 404 for wrong tenant (avoid leaking existence of other tenants).
    """
    # SUPER_ADMIN can access any tenant (e.g. get/update/delete any tenant by id).
    if current_user.role == UserRole.SUPER_ADMIN:
        return
    # TENANT_ADMIN and others: must belong to this tenant. Use 404 so we don't reveal other tenants exist.
    if current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
