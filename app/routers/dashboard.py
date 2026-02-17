"""Dashboard route: GET /users/{user_id}/dashboard/stats. Role-scoped (own, intern, or any tenant user)."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.init_db import get_db
from app.dependencies.tenant import get_current_tenant
from app.dependencies.user import get_current_user
from app.models import Tenant, User
from app.services import dashboard_service

# Mounted under users router so full path is /users/{user_id}/dashboard/stats. get_current_tenant enforces tenant scope (SUPER_ADMIN has no tenant).
router = APIRouter(tags=["Dashboard"])


@router.get("/{user_id}/dashboard/stats")
async def get_user_dashboard_stats(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Dashboard stats for a user. INTERN: own only; MENTOR: own or intern; TENANT_ADMIN: any user in tenant. Service returns 403 if user_id not allowed."""
    return await dashboard_service.get_stats_for_user(db, user_id, current_user)
