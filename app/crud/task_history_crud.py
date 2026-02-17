"""Task history CRUD: append status/priority changes and list by task. Append-only audit log; no update or delete. Service calls create when task status/priority changes."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import TaskPriority, TaskStatus
from app.models import TaskHistory


async def create_history_entry(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    task_id: UUID,
    actor_id: UUID,
    old_status: TaskStatus | None = None,
    new_status: TaskStatus | None = None,
    old_priority: TaskPriority | None = None,
    new_priority: TaskPriority | None = None,
) -> TaskHistory:
    """Append one history row (status and/or priority change). Caller passes old/new values; at least one pair should differ for a meaningful entry."""
    entry = TaskHistory(
        tenant_id=tenant_id,
        task_id=task_id,
        actor_id=actor_id,
        old_status=old_status,
        new_status=new_status,
        old_priority=old_priority,
        new_priority=new_priority,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


async def get_history_for_task(
    db: AsyncSession,
    task_id: UUID,
    tenant_id: UUID | None = None,
    skip: int = 0,
    limit: int = 20,
) -> list[TaskHistory]:
    """List history for a task (newest first, paginated). Pass tenant_id to restrict to tenant (service does this for scope)."""
    q = (
        select(TaskHistory)
        .where(TaskHistory.task_id == task_id)
        .order_by(TaskHistory.created_at.desc())
    )
    if tenant_id is not None:
        q = q.where(TaskHistory.tenant_id == tenant_id)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())
