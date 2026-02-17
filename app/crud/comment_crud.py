"""Comment CRUD: get, get with details, list by task, create, update, soft-delete. All scoped by task and tenant; service layer enforces access."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Comment, Task, User


async def get_comment(
    db: AsyncSession,
    comment_id: UUID,
    task_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> Comment | None:
    """Get comment by id; exclude soft-deleted. Pass task_id/tenant_id to ensure comment belongs to scope (service does this)."""
    q = select(Comment).where(Comment.id == comment_id, Comment.deleted_at.is_(None))
    if task_id is not None:
        q = q.where(Comment.task_id == task_id)
    if tenant_id is not None:
        q = q.where(Comment.tenant_id == tenant_id)
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def get_comment_with_details(
    db: AsyncSession,
    comment_id: UUID,
    task_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> Comment | None:
    """Get comment with tenant, task (owner, assignee, tenant), and user eager-loaded. unique() dedupes rows from joinedload."""
    q = (
        select(Comment)
        .where(Comment.id == comment_id, Comment.deleted_at.is_(None))
        .options(
            joinedload(Comment.tenant),
            joinedload(Comment.task).options(
                joinedload(Task.owner).joinedload(User.tenant),
                joinedload(Task.assignee).joinedload(User.tenant),
                joinedload(Task.tenant),
            ),
            joinedload(Comment.user).joinedload(User.tenant),
        )
    )
    if task_id is not None:
        q = q.where(Comment.task_id == task_id)
    if tenant_id is not None:
        q = q.where(Comment.tenant_id == tenant_id)
    result = await db.execute(q)
    return result.unique().scalar_one_or_none()


async def get_comments_by_task(
    db: AsyncSession,
    task_id: UUID,
    tenant_id: UUID | None = None,
    skip: int = 0,
    limit: int = 20,
) -> list[Comment]:
    """List comments for a task (paginated, newest first); exclude soft-deleted. Optional tenant_id for scope."""
    q = (
        select(Comment)
        .where(Comment.task_id == task_id, Comment.deleted_at.is_(None))
        .order_by(Comment.created_at.desc())
    )
    if tenant_id is not None:
        q = q.where(Comment.tenant_id == tenant_id)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


async def create_comment(db: AsyncSession, **kwargs) -> Comment:
    """Create a comment. Caller must pass tenant_id, task_id, user_id, message (and optionally reason)."""
    comment = Comment(**kwargs)
    db.add(comment)
    await db.flush()
    await db.refresh(comment)
    return comment


async def update_comment(
    db: AsyncSession, comment_id: UUID, **updates
) -> Comment | None:
    """Update comment by id. Uses get_comment so soft-deleted comments are not updated. Returns None if not found."""
    comment = await get_comment(db, comment_id)
    if not comment:
        return None
    for key, value in updates.items():
        if hasattr(comment, key):
            setattr(comment, key, value)
    await db.flush()
    await db.refresh(comment)
    return comment


async def soft_delete_comment(
    db: AsyncSession, comment_id: UUID, deleted_by: UUID | None = None
) -> bool:
    """Soft-delete comment (SoftDeleteMixin: sets deleted_at, deleted_by). Returns True if comment existed and was deleted."""
    comment = await get_comment(db, comment_id)
    if not comment:
        return False
    comment.soft_delete(deleted_by)
    await db.flush()
    return True
