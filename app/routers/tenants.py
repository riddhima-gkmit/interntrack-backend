"""Tenant routes: register (self), list/get/create/update/delete. SUPER_ADMIN for platform; TENANT_ADMIN for own tenant only."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.init_db import get_db
from app.dependencies.permissions import (
    require_super_admin_for_tenant_apis,
    require_tenant_admin_or_super_for_tenant_apis,
)
from app.dependencies.rate_limit import rate_limit_public
from app.models import User
from app.schemas.tenant import (
    TenantCreateSchema,
    TenantRegisterSchema,
    TenantUpdateSchema,
)
from app.services import tenant_service

# /register is public (no auth); other routes use require_super_admin or require_tenant_admin_or_super.
router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
)
async def tenant_register(
    data: TenantRegisterSchema,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_public),
):
    """Tenant self-registration. Public: anyone can register a new organization (tenant + first user as TENANT_ADMIN)."""
    return await tenant_service.register_tenant(
        db, data, background_tasks=background_tasks
    )


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
)
async def create_tenant(
    data: TenantCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin_for_tenant_apis),
):
    """Create tenant (SUPER_ADMIN only). Mentors cannot access."""
    return await tenant_service.create_tenant(db, data)


@router.get("/")
async def list_tenants(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin_for_tenant_apis),
    page: int = Query(1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(10, ge=1, le=100, description="Items per page."),
    is_active: bool | None = Query(None),
):
    """List tenants with pagination (SUPER_ADMIN only). Mentors cannot access."""
    skip = (page - 1) * page_size
    limit = page_size
    # is_active filter: None = all, True/False = filter by active flag.
    return await tenant_service.list_tenants(
        db, skip=skip, limit=limit, is_active=is_active
    )


@router.get("/{tenant_id}/")
async def get_tenant(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tenant_admin_or_super_for_tenant_apis),
):
    """Get tenant by ID. TENANT_ADMIN: own only (404 if tenant_id != current_user.tenant_id); SUPER_ADMIN: any."""
    return await tenant_service.get_tenant(db, tenant_id, current_user)


@router.patch("/{tenant_id}/")
async def update_tenant(
    tenant_id: UUID,
    data: TenantUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tenant_admin_or_super_for_tenant_apis),
):
    """Update tenant. TENANT_ADMIN: own only (404 if wrong tenant); SUPER_ADMIN: any. Service enforces scope."""
    return await tenant_service.update_tenant(db, tenant_id, data, current_user)


@router.delete("/{tenant_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tenant_admin_or_super_for_tenant_apis),
):
    """Soft-delete tenant (deleted_at/deleted_by). Service rejects if tenant has active users; enforces TENANT_ADMIN = own only."""
    await tenant_service.delete_tenant(db, tenant_id, current_user)
