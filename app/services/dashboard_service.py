"""Dashboard service: aggregate stats for a user (tasks by status/priority, comments); super-admin tenant dashboard (tenant counts, list summary). Role-scoped: INTERN own; MENTOR own or intern; TENANT_ADMIN any in tenant. SUPER_ADMIN has no tenant → 403 for user dashboard."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import tenant_crud, user_crud
from app.enums import TaskPriority, TaskStatus, UserRole
from app.models import Comment, Task, User
from app.utils.response_helpers import success_response


async def get_stats_for_user(
    db: AsyncSession, user_id: UUID, current_user: User
) -> dict:
    """Dashboard stats for target user. Checks: current_user has tenant → target exists → same tenant (404 if not) → role (INTERN own only, MENTOR own or intern, TENANT_ADMIN any)."""
    if current_user.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Dashboard is available only to users with a tenant.",
        )
    target_user = await user_crud.get_user(db, user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    if target_user.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    if current_user.role == UserRole.INTERN:
        if user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view your own dashboard stats.",
            )
    elif current_user.role == UserRole.MENTOR:
        if user_id != current_user.id and target_user.role != UserRole.INTERN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Mentors can only view their own stats or an intern's stats.",
            )
    return success_response(await _stats_intern(db, current_user.tenant_id, user_id))


async def _stats_intern(db: AsyncSession, tenant_id: UUID, user_id: UUID) -> dict:
    """Aggregate stats for a user: tasks where they are assignee or owner (exclude soft-deleted); comments on those tasks."""
    total = (
        await db.scalar(
            select(func.count(Task.id)).where(
                Task.tenant_id == tenant_id,
                Task.deleted_at.is_(None),
                or_(Task.assignee_id == user_id, Task.owner_id == user_id),
            )
        )
        or 0
    )
    total_pending = (
        await db.scalar(
            select(func.count(Task.id)).where(
                Task.tenant_id == tenant_id,
                Task.deleted_at.is_(None),
                or_(Task.assignee_id == user_id, Task.owner_id == user_id),
                Task.status == TaskStatus.PENDING,
            )
        )
        or 0
    )
    total_in_progress = (
        await db.scalar(
            select(func.count(Task.id)).where(
                Task.tenant_id == tenant_id,
                Task.deleted_at.is_(None),
                or_(Task.assignee_id == user_id, Task.owner_id == user_id),
                Task.status == TaskStatus.IN_PROGRESS,
            )
        )
        or 0
    )
    total_completed = (
        await db.scalar(
            select(func.count(Task.id)).where(
                Task.tenant_id == tenant_id,
                Task.deleted_at.is_(None),
                or_(Task.assignee_id == user_id, Task.owner_id == user_id),
                Task.status == TaskStatus.COMPLETED,
            )
        )
        or 0
    )
    total_high_priority = (
        await db.scalar(
            select(func.count(Task.id)).where(
                Task.tenant_id == tenant_id,
                Task.deleted_at.is_(None),
                or_(Task.assignee_id == user_id, Task.owner_id == user_id),
                Task.priority == TaskPriority.HIGH,
            )
        )
        or 0
    )
    # Comments on tasks where user is assignee or owner; exclude soft-deleted task and comment.
    total_comments = (
        await db.scalar(
            select(func.count(Comment.id))
            .join(Task, Comment.task_id == Task.id)
            .where(
                Task.tenant_id == tenant_id,
                Task.deleted_at.is_(None),
                Comment.deleted_at.is_(None),
                or_(Task.assignee_id == user_id, Task.owner_id == user_id),
            )
        )
        or 0
    )
    return {
        "total_tasks": total,
        "total_pending_tasks": total_pending,
        "total_in_progress_tasks": total_in_progress,
        "total_completed_tasks": total_completed,
        "total_high_priority_tasks": total_high_priority,
        "total_comments": total_comments,
    }


async def get_superadmin_tenant_stats(db: AsyncSession) -> dict:
    """Platform-level tenant stats for super admin: total tenants, soft-deleted count/list, and per-tenant summary (name, is_active, created_at, user count, tenant_admin count)."""
    total_tenants = await tenant_crud.count_tenants(db, include_deleted=False)
    soft_deleted_count = await tenant_crud.count_tenants(db, only_deleted=True)
    soft_deleted_list = await tenant_crud.get_tenants(
        db, skip=0, limit=50, only_deleted=True
    )
    tenants = await tenant_crud.get_tenants(
        db, skip=0, limit=500
    )
    tenant_ids = [t.id for t in tenants]
    if not tenant_ids:
        return success_response({
            "total_tenants": 0,
            "deleted_tenants": {"count": soft_deleted_count, "list": _serialize_tenant_list(soft_deleted_list)},
            "tenant_list_summary": [],
        })
    # Per-tenant user counts (non-deleted users) and tenant_admin counts in two queries to avoid N+1.
    total_by_tenant = await _user_counts_by_tenant(db, tenant_ids, role=None)
    admin_by_tenant = await _user_counts_by_tenant(db, tenant_ids, role=UserRole.TENANT_ADMIN)
    summary = [
        {
            "id": str(t.id),
            "name": t.name,
            "is_active": t.is_active,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "user_count": total_by_tenant.get(t.id, 0),
            "tenant_admin_count": admin_by_tenant.get(t.id, 0),
        }
        for t in tenants
    ]
    return success_response({
        "total_tenants": total_tenants,
        "deleted_tenants": {
            "count": soft_deleted_count,
            "list": _serialize_tenant_list(soft_deleted_list),
        },
        "tenant_list_summary": summary,
    })


async def _user_counts_by_tenant(
    db: AsyncSession, tenant_ids: list[UUID], role: UserRole | None
) -> dict[UUID, int]:
    """Return dict tenant_id -> count of non-deleted users (optionally filtered by role)."""
    q = (
        select(User.tenant_id, func.count(User.id))
        .where(User.tenant_id.in_(tenant_ids), User.deleted_at.is_(None))
    )
    if role is not None:
        q = q.where(User.role == role)
    q = q.group_by(User.tenant_id)
    result = await db.execute(q)
    return {row[0]: row[1] for row in result.all()}


def _serialize_tenant_list(tenants: list) -> list[dict]:
    """Serialize tenant list for soft-deleted response (id, name, is_active, created_at, deleted_at)."""
    return [
        {
            "id": str(t.id),
            "name": t.name,
            "is_active": t.is_active,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "deleted_at": t.deleted_at.isoformat() if getattr(t, "deleted_at", None) else None,
        }
        for t in tenants
    ]
