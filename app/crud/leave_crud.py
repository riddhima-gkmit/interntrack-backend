"""Leave CRUD: get (with details), list, count, create, update, soft-delete, overlap check. All list/count/get scoped by tenant; service enforces who can see what."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.enums import LeaveStatus, LeaveType
from app.models import Leave, User


async def get_leave_with_details(
    db: AsyncSession,
    leave_id: UUID,
    tenant_id: UUID | None = None,
    include_deleted: bool = False,
) -> Leave | None:
    """Get leave with tenant, user, approver eager-loaded. unique() dedupes joinedload rows; optional tenant_id for scope."""
    q = (
        select(Leave)
        .options(
            joinedload(Leave.tenant),
            joinedload(Leave.user).joinedload(User.tenant),
            joinedload(Leave.approver).joinedload(User.tenant),
        )
        .where(Leave.id == leave_id)
    )
    if not include_deleted:
        q = q.where(Leave.deleted_at.is_(None))
    if tenant_id is not None:
        q = q.where(Leave.tenant_id == tenant_id)
    result = await db.execute(q)
    return result.unique().scalar_one_or_none()


async def get_leave(
    db: AsyncSession,
    leave_id: UUID,
    tenant_id: UUID | None = None,
    include_deleted: bool = False,
) -> Leave | None:
    """Get leave by id (no joins). Pass tenant_id to restrict to tenant; exclude soft-deleted unless include_deleted."""
    q = select(Leave).where(Leave.id == leave_id)
    if not include_deleted:
        q = q.where(Leave.deleted_at.is_(None))
    if tenant_id is not None:
        q = q.where(Leave.tenant_id == tenant_id)
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def get_leaves(
    db: AsyncSession,
    tenant_id: UUID,
    skip: int = 0,
    limit: int = 10,
    status: LeaveStatus | None = None,
    leave_type: LeaveType | None = None,
    user_id: UUID | None = None,
    user_ids: list[UUID] | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[Leave]:
    """List leaves in tenant (newest first); optional filters: status, type, user_id or user_ids, date range. Paginated; excludes soft-deleted."""
    q = (
        select(Leave)
        .where(
            Leave.tenant_id == tenant_id,
            Leave.deleted_at.is_(None),
        )
        .order_by(Leave.created_at.desc())
    )
    if status is not None:
        q = q.where(Leave.status == status)
    if leave_type is not None:
        q = q.where(Leave.leave_type == leave_type)
    if user_id is not None:
        q = q.where(Leave.user_id == user_id)
    if user_ids is not None:
        q = q.where(Leave.user_id.in_(user_ids))
    if start_date is not None:
        q = q.where(Leave.start_date >= start_date)
    if end_date is not None:
        q = q.where(Leave.end_date <= end_date)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


async def count_leaves(
    db: AsyncSession,
    tenant_id: UUID,
    status: LeaveStatus | None = None,
    leave_type: LeaveType | None = None,
    user_id: UUID | None = None,
    user_ids: list[UUID] | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> int:
    """Total count with same filters as get_leaves (for pagination total)."""
    from sqlalchemy import func

    q = select(func.count(Leave.id)).where(
        Leave.tenant_id == tenant_id,
        Leave.deleted_at.is_(None),
    )
    if status is not None:
        q = q.where(Leave.status == status)
    if leave_type is not None:
        q = q.where(Leave.leave_type == leave_type)
    if user_id is not None:
        q = q.where(Leave.user_id == user_id)
    if user_ids is not None:
        q = q.where(Leave.user_id.in_(user_ids))
    if start_date is not None:
        q = q.where(Leave.start_date >= start_date)
    if end_date is not None:
        q = q.where(Leave.end_date <= end_date)
    result = await db.execute(q)
    return result.scalar() or 0


async def has_overlapping_leave(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    start_date: datetime,
    end_date: datetime,
) -> bool:
    """True if this user has any non-deleted leave in tenant whose [start_date, end_date] overlaps the given range. Service may exclude current leave id when updating."""
    q = (
        select(Leave.id)
        .where(
            Leave.tenant_id == tenant_id,
            Leave.user_id == user_id,
            Leave.deleted_at.is_(None),
            Leave.start_date <= end_date,
            Leave.end_date >= start_date,
        )
        .limit(1)
    )
    result = await db.execute(q)
    return result.scalar_one_or_none() is not None


async def create_leave(db: AsyncSession, **kwargs) -> Leave:
    """Create a leave. Caller supplies tenant_id, user_id, start_date, end_date, leave_type, status, reason, etc."""
    leave = Leave(**kwargs)
    db.add(leave)
    await db.flush()
    await db.refresh(leave)
    return leave


async def update_leave(db: AsyncSession, leave_id: UUID, **updates) -> Leave | None:
    """Update leave by id. Uses get_leave so soft-deleted are skipped; only provided fields are updated. Returns None if not found."""
    leave = await get_leave(db, leave_id)
    if not leave:
        return None
    for key, value in updates.items():
        if hasattr(leave, key):
            setattr(leave, key, value)
    await db.flush()
    await db.refresh(leave)
    return leave


async def soft_delete_leave(
    db: AsyncSession,
    leave_id: UUID,
    tenant_id: UUID | None = None,
    deleted_by: UUID | None = None,
) -> bool:
    """Soft-delete leave (SoftDeleteMixin). Pass tenant_id to restrict to tenant; returns True if leave existed and was deleted."""
    leave = await get_leave(db, leave_id, tenant_id=tenant_id)
    if not leave:
        return False
    leave.soft_delete(deleted_by)
    await db.flush()
    return True
