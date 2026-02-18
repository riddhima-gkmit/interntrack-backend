"""Dashboard routes: user dashboard stats and super-admin tenant stats."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.init_db import get_db
from app.dependencies.permissions import require_super_admin_for_tenant_apis
from app.dependencies.tenant import get_current_tenant
from app.dependencies.user import get_current_user
from app.models import Tenant, User
from app.services import dashboard_service

# Mounted under api_v1: /users/{user_id}/dashboard/stats and /dashboard/stats (no prefix on include).
router = APIRouter(tags=["Dashboard"])


@router.get("/users/{user_id}/dashboard/stats")
async def get_user_dashboard_stats(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Dashboard stats for a user. INTERN: own only; MENTOR: own or intern; TENANT_ADMIN: any user in tenant. Service returns 403 if user_id not allowed."""
    return await dashboard_service.get_stats_for_user(db, user_id, current_user)


@router.get("/tenants/dashboard/stats")
async def get_tenants_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin_for_tenant_apis),
):
    """Super-admin only: platform tenant stats (total tenants, soft-deleted count/list, tenant list summary with user and tenant_admin counts)."""
    return await dashboard_service.get_superadmin_tenant_stats(db)
