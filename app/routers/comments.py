"""Comment routes: list, get, create, update, delete under /tasks/{task_id}/comments/. Access follows task scope."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.init_db import get_db
from app.dependencies.tenant import get_current_tenant
from app.dependencies.user import get_current_user
from app.models import Tenant, User
from app.schemas.comment import CommentCreateSchema, CommentUpdateSchema
from app.services import comment_service

# Mounted under tasks router so full path is e.g. /tasks/{task_id}/comments/. get_current_user then get_current_tenant enforce JWT + tenant scope.
router = APIRouter(tags=["Comments"])


@router.get("/{task_id}/comments/")
async def list_comments(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    page: int = Query(1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(20, ge=1, le=100, description="Items per page."),
):
    """List comments for a task. Scope: same as task access."""
    # Convert 1-based page to skip/limit for DB query; service checks task is in tenant.
    skip = (page - 1) * page_size
    limit = page_size
    return await comment_service.list_comments(
        db, task_id, current_user, skip=skip, limit=limit
    )


@router.get("/{task_id}/comments/{comment_id}/")
async def get_comment(
    task_id: UUID,
    comment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Get comment by ID. Scope: same as task access; service returns 404 if task or comment not in tenant."""
    return await comment_service.get_comment_by_id(
        db, task_id, comment_id, current_user
    )


@router.post("/{task_id}/comments/", status_code=status.HTTP_201_CREATED)
async def create_comment(
    task_id: UUID,
    data: CommentCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Add comment to task. Scope: same as task access; service sets current_user as comment author."""
    return await comment_service.create_comment(db, task_id, data.message, current_user)


@router.patch("/{task_id}/comments/{comment_id}/")
async def update_comment(
    task_id: UUID,
    comment_id: UUID,
    data: CommentUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Update comment. Service enforces INTERN = own comments only; MENTOR/ADMIN can update any in-scope comment."""
    return await comment_service.update_comment(
        db, task_id, comment_id, data.message, current_user
    )


@router.delete(
    "/{task_id}/comments/{comment_id}/", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_comment(
    task_id: UUID,
    comment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Delete comment. Service enforces INTERN = own comments only; MENTOR/ADMIN can delete any in-scope comment."""
    await comment_service.delete_comment(db, task_id, comment_id, current_user)
