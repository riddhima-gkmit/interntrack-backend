"""Leave routes: list, get, create, update, delete. Tenant admin passes user_id via header for create."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.init_db import get_db
from app.dependencies.tenant import get_current_tenant
from app.dependencies.user import get_current_user
from app.enums import LeaveStatus, LeaveType, UserRole
from app.models import Tenant, User
from app.schemas.leave import LeaveCreateSchema, LeaveUpdateSchema
from app.services import leave_service

# All routes require JWT + tenant (get_current_tenant). SUPER_ADMIN has no tenant and is handled by dependency.
router = APIRouter(prefix="/leaves", tags=["Leaves"])


def _parse_leave_type(v: str | None) -> LeaveType | None:
    """Normalize to lowercase and parse; return None if empty or invalid (caller can then return 422 if value was provided)."""
    if not v or not v.strip():
        return None
    try:
        return LeaveType(v.strip().lower())
    except ValueError:
        return None


def _parse_leave_status(v: str | None) -> LeaveStatus | None:
    """Normalize to lowercase and parse; return None if empty or invalid."""
    if not v or not v.strip():
        return None
    try:
        return LeaveStatus(v.strip().lower())
    except ValueError:
        return None


@router.get("/")
async def list_leaves(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    page: int = Query(1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(10, ge=1, le=100, description="Items per page."),
    leave_type: str | None = Query(
        None,
        description="Filter by leave type (e.g. vacation, sick, personal, other). Any casing accepted.",
    ),
    status: str | None = Query(
        None,
        description="Filter by status (e.g. pending, approved, rejected, cancelled). Any casing accepted.",
    ),
    start_date: datetime | None = Query(
        None, description="Filter leaves that start on or after this date (ISO 8601)."
    ),
    end_date: datetime | None = Query(
        None, description="Filter leaves that end on or before this date (ISO 8601)."
    ),
    user_id: UUID | None = Query(None, description="Filter by user ID (tenant scope)."),
):
    """List leaves (role-filtered). Optional filters: leave_type, status, start_date, end_date, user_id."""
    skip = (page - 1) * page_size
    limit = page_size
    _leave_type = _parse_leave_type(leave_type)
    _status = _parse_leave_status(status)
    # If client sent leave_type/status but value is invalid, return 422 with allowed values.
    if leave_type is not None and _leave_type is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid leave_type. Must be one of: sick, vacation, personal, other.",
        )
    if status is not None and _status is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid status. Must be one of: pending, approved, rejected, cancelled.",
        )
    # tenant.id scopes query; service applies role filter (INTERN=own, MENTOR=team, TENANT_ADMIN=all in tenant).
    return await leave_service.list_leaves(
        db,
        current_user,
        tenant.id,
        skip=skip,
        limit=limit,
        status=_status,
        leave_type=_leave_type,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/{leave_id}/")
async def get_leave(
    leave_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Get leave by ID. Returns 404 for wrong tenant or out of scope."""
    return await leave_service.get_leave_by_id(db, leave_id, current_user, tenant.id)


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_leave(
    data: LeaveCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    x_user_id: UUID | None = Header(
        None,
        alias="user_id",
        description="Tenant admin: user ID to create leave for (intern/mentor).",
    ),
):
    """Request leave. TENANT_ADMIN must pass user_id via the user_id header to create leave for a mentor/intern (then status=approved)."""
    # INTERN/MENTOR: user_id stays None so service creates leave for current_user. TENANT_ADMIN: must pass user_id header (create on behalf of).
    user_id: UUID | None = None
    if current_user.role == UserRole.TENANT_ADMIN:
        user_id = x_user_id
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="user_id is required when tenant admin creates leave. Pass it in the user_id header.",
            )
    return await leave_service.create_leave(
        db,
        leave_type=data.leave_type,
        start_date=data.start_date,
        end_date=data.end_date,
        reason=data.reason,
        current_user=current_user,
        tenant_id=tenant.id,
        user_id=user_id,
    )


@router.patch("/{leave_id}/")
async def update_leave(
    leave_id: UUID,
    data: LeaveUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Update leave: all body fields optional (null). Only provided fields are updated. Service enforces role (e.g. only admin can approve/reject)."""
    return await leave_service.update_leave(
        db,
        leave_id,
        current_user,
        tenant.id,
        new_status=data.status,
        leave_type=data.leave_type,
        start_date=data.start_date,
        end_date=data.end_date,
    )


@router.delete("/{leave_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_leave(
    leave_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Soft-delete leave (TENANT_ADMIN only). Service sets deleted_at/deleted_by and returns 403 for non-admin."""
    await leave_service.delete_leave(db, leave_id, current_user, tenant.id)
