"""Task CRUD: get, list, count, create, update, soft-delete, and lookup by owner/assignee/title for uniqueness. All scoped by tenant; service enforces access."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.enums import TaskPriority, TaskStatus
from app.models import Task, User


async def get_task(
    db: AsyncSession, task_id: UUID, tenant_id: UUID | None = None
) -> Task | None:
    """Get task with owner, assignee, tenant eager-loaded. unique() dedupes joinedload; optional tenant_id for scope; excludes soft-deleted."""
    q = (
        select(Task)
        .where(Task.id == task_id, Task.deleted_at.is_(None))
        .options(
            joinedload(Task.owner).joinedload(User.tenant),
            joinedload(Task.assignee).joinedload(User.tenant),
            joinedload(Task.tenant),
        )
    )
    if tenant_id is not None:
        q = q.where(Task.tenant_id == tenant_id)
    result = await db.execute(q)
    return result.unique().scalar_one_or_none()


async def get_tasks(
    db: AsyncSession,
    tenant_id: UUID,
    skip: int = 0,
    limit: int = 10,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    assignee_id: UUID | None = None,
    owner_id: UUID | None = None,
) -> list[Task]:
    """List tasks in tenant (newest first); optional filters: status, priority, assignee_id, owner_id. Paginated; owner/assignee/tenant eager-loaded; excludes soft-deleted."""
    q = (
        select(Task)
        .where(
            Task.tenant_id == tenant_id,
            Task.deleted_at.is_(None),
        )
        .options(
            joinedload(Task.owner).joinedload(User.tenant),
            joinedload(Task.assignee).joinedload(User.tenant),
            joinedload(Task.tenant),
        )
        .order_by(Task.created_at.desc())
    )
    if status is not None:
        q = q.where(Task.status == status)
    if priority is not None:
        q = q.where(Task.priority == priority)
    if assignee_id is not None:
        q = q.where(Task.assignee_id == assignee_id)
    if owner_id is not None:
        q = q.where(Task.owner_id == owner_id)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return list(result.unique().scalars().all())


async def get_task_by_owner_assignee_title(
    db: AsyncSession,
    tenant_id: UUID,
    owner_id: UUID,
    assignee_id: UUID,
    title: str,
    exclude_task_id: UUID | None = None,
) -> Task | None:
    """Find task with same tenant, owner, assignee, title (uniqueness). Pass exclude_task_id when updating so current task is not counted as duplicate."""
    q = select(Task).where(
        Task.tenant_id == tenant_id,
        Task.owner_id == owner_id,
        Task.assignee_id == assignee_id,
        Task.title == title,
        Task.deleted_at.is_(None),
    )
    if exclude_task_id is not None:
        q = q.where(Task.id != exclude_task_id)
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def count_tasks(
    db: AsyncSession,
    tenant_id: UUID,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    assignee_id: UUID | None = None,
    owner_id: UUID | None = None,
) -> int:
    """Total count with same filters as get_tasks (for pagination total)."""
    from sqlalchemy import func

    q = select(func.count(Task.id)).where(
        Task.tenant_id == tenant_id,
        Task.deleted_at.is_(None),
    )
    if status is not None:
        q = q.where(Task.status == status)
    if priority is not None:
        q = q.where(Task.priority == priority)
    if assignee_id is not None:
        q = q.where(Task.assignee_id == assignee_id)
    if owner_id is not None:
        q = q.where(Task.owner_id == owner_id)
    result = await db.execute(q)
    return result.scalar() or 0


async def create_task(db: AsyncSession, **kwargs) -> Task:
    """Create a task. Caller supplies tenant_id, owner_id, assignee_id, title, description, status, priority, due_date, etc."""
    task = Task(**kwargs)
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


async def update_task(db: AsyncSession, task_id: UUID, **updates) -> Task | None:
    """Update task by id. Uses get_task so soft-deleted are skipped; tenant_id is not updatable. Returns None if not found."""
    task = await get_task(db, task_id)
    if not task:
        return None
    for key, value in updates.items():
        if hasattr(task, key) and key != "tenant_id":
            setattr(task, key, value)
    await db.flush()
    await db.refresh(task)
    return task


async def soft_delete_task(
    db: AsyncSession,
    task_id: UUID,
    tenant_id: UUID | None = None,
    deleted_by: UUID | None = None,
) -> bool:
    """Soft-delete task (SoftDeleteMixin). Pass tenant_id to restrict to tenant; returns True if task existed and was deleted."""
    task = await get_task(db, task_id, tenant_id)
    if not task:
        return False
    task.soft_delete(deleted_by)
    await db.flush()
    return True
