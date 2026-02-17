"""Task routes: list, get, create, update, delete, history. assignee_id can be sent in header or body."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.init_db import get_db
from app.dependencies.tenant import get_current_tenant
from app.dependencies.user import get_current_user
from app.enums import TaskPriority, TaskStatus
from app.models import Tenant, User
from app.schemas.task import TaskCreateSchema, TaskUpdateSchema
from app.services import task_service

# All routes require JWT + tenant. assignee_id for create can come from header (or body via schema if supported).
router = APIRouter(prefix="/tasks", tags=["Tasks"])


def _parse_task_status(value: str | None) -> TaskStatus | None:
    """Parse status from query param; accept any casing. Raises 422 if value provided but invalid."""
    if value is None:
        return None
    normalized = value.strip().lower()
    try:
        return TaskStatus(normalized)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid status. Use: pending, in_progress, completed",
        )


def _parse_task_priority(value: str | None) -> TaskPriority | None:
    """Parse priority from query param; accept any casing. Raises 422 if value provided but invalid."""
    if value is None:
        return None
    normalized = value.strip().lower()
    try:
        return TaskPriority(normalized)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid priority. Use: low, medium, high",
        )


@router.get("/")
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    page: int = Query(1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(10, ge=1, le=100, description="Items per page."),
    status: str | None = Query(None, description="Filter by status (any casing)."),
    priority: str | None = Query(None, description="Filter by priority (any casing)."),
    assignee_id: UUID | None = Query(None),
    owner_id: UUID | None = Query(None),
):
    """List tasks (role-scoped). Service filters by role (INTERN=own/assigned, MENTOR=team, TENANT_ADMIN=all in tenant)."""
    skip = (page - 1) * page_size
    limit = page_size
    status_enum = _parse_task_status(status)
    priority_enum = _parse_task_priority(priority)
    return await task_service.list_tasks(
        db,
        current_user,
        tenant.id,
        skip=skip,
        limit=limit,
        status=status_enum,
        priority=priority_enum,
        assignee_id=assignee_id,
        owner_id=owner_id,
    )


@router.get("/{task_id}/")
async def get_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Get task by ID. Service returns 404 if task not in tenant or not visible to current_user role."""
    return await task_service.get_task(db, task_id, current_user)


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_task(
    data: TaskCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    assignee_id_header: UUID | None = Header(
        None,
        alias="assignee_id",
        description="Assignee user ID (can be passed in header or body).",
    ),
):
    """Create task. INTERN: assignee must be self. assignee_id can be sent in assignee_id header or in body."""
    assignee_id = assignee_id_header
    if assignee_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="assignee_id is required. Pass it in the header.",
        )
    # Service enforces INTERN can only set assignee_id = current_user; MENTOR/ADMIN can assign any user in tenant.
    return await task_service.create_task(
        db, data, current_user, tenant.id, assignee_id=assignee_id
    )


@router.patch("/{task_id}/")
async def update_task(
    task_id: UUID,
    data: TaskUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Update task. Service writes TaskHistory rows for status/priority changes and enforces role (e.g. INTERN limited)."""
    return await task_service.update_task(db, task_id, data, current_user)


@router.delete("/{task_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Soft-delete task (deleted_at/deleted_by). Service enforces INTERN only if owner == self; 403 otherwise."""
    await task_service.delete_task(db, task_id, current_user)


@router.get("/{task_id}/history/")
async def get_task_history(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    page: int = Query(1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(20, ge=1, le=100, description="Items per page."),
):
    """Get task history (status/priority changes only). Service returns 404 if task not in scope."""
    skip = (page - 1) * page_size
    limit = page_size
    return await task_service.get_task_history(
        db, task_id, current_user, skip=skip, limit=limit
    )
