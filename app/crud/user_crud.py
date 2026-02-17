"""User CRUD: get (incl. deleted), get by email/username (CI, tenant-scoped or any-tenant), list, count, create, update, soft-delete/restore with cascade. Service enforces tenant/role access."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import UserRole
from app.models import Comment, Invitation, Leave, Task, User


async def get_user(db: AsyncSession, user_id: UUID) -> User | None:
    """Get user by id; excludes soft-deleted. Use get_user_include_deleted for restore flow."""
    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def get_user_include_deleted(db: AsyncSession, user_id: UUID) -> User | None:
    """Get user by id including soft-deleted (e.g. restore or audit)."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_email_ci(
    db: AsyncSession, email: str, tenant_id: UUID | None = None
) -> User | None:
    """Get user by email (case-insensitive). tenant_id=None means only users with no tenant (e.g. pre-invite); tenant_id set = that tenant. Excludes soft-deleted."""
    email_lower = email.lower().strip()
    q = select(User).where(
        func.lower(User.email) == email_lower,
        User.deleted_at.is_(None),
    )
    if tenant_id is not None:
        q = q.where(User.tenant_id == tenant_id)
    else:
        q = q.where(User.tenant_id.is_(None))
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def get_user_by_email_any_tenant(db: AsyncSession, email: str) -> User | None:
    """Get user by email (case-insensitive), any tenant or no tenant. For auth when tenant is unknown. Excludes soft-deleted; one row expected (email unique globally)."""
    email_lower = email.lower().strip()
    result = await db.execute(
        select(User).where(
            func.lower(User.email) == email_lower,
            User.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def get_user_by_email_any_tenant_include_deleted(
    db: AsyncSession, email: str
) -> User | None:
    """Get user by email (case-insensitive), any tenant, including soft-deleted (e.g. block re-register with same email)."""
    email_lower = email.lower().strip()
    result = await db.execute(select(User).where(func.lower(User.email) == email_lower))
    return result.scalar_one_or_none()


async def get_user_by_username_ci(
    db: AsyncSession, username: str, tenant_id: UUID | None = None
) -> User | None:
    """Get user by username (case-insensitive). tenant_id scopes to that tenant or to no-tenant (tenant_id=None). Excludes soft-deleted; username unique per tenant."""
    username_lower = username.lower().strip()
    q = select(User).where(
        func.lower(User.username) == username_lower,
        User.deleted_at.is_(None),
    )
    if tenant_id is not None:
        q = q.where(User.tenant_id == tenant_id)
    else:
        q = q.where(User.tenant_id.is_(None))
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def get_user_by_username_ci_include_deleted(
    db: AsyncSession, username: str, tenant_id: UUID | None = None
) -> User | None:
    """Get user by username (case-insensitive), including soft-deleted (e.g. restore or duplicate-check before create). Same tenant/no-tenant scoping as get_user_by_username_ci."""
    username_lower = username.lower().strip()
    q = select(User).where(func.lower(User.username) == username_lower)
    if tenant_id is not None:
        q = q.where(User.tenant_id == tenant_id)
    else:
        q = q.where(User.tenant_id.is_(None))
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def get_user_by_username_any_tenant(
    db: AsyncSession, username: str
) -> User | None:
    """Get user by username (case-insensitive) in any tenant. Excludes soft-deleted; limit(1) so first match if same username in multiple tenants."""
    username_lower = username.lower().strip()
    result = await db.execute(
        select(User)
        .where(
            func.lower(User.username) == username_lower,
            User.deleted_at.is_(None),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def count_active_users_by_tenant(db: AsyncSession, tenant_id: UUID) -> int:
    """Count non-deleted, is_active=True users in tenant. Used to block tenant delete when tenant still has active users."""
    q = select(func.count(User.id)).where(
        User.tenant_id == tenant_id,
        User.deleted_at.is_(None),
        User.is_active.is_(True),
    )
    result = await db.execute(q)
    return result.scalar() or 0


async def get_users(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 10,
    tenant_id: UUID | None = None,
    role: UserRole | None = None,
    is_active: bool | None = None,
    is_deleted: bool | None = None,
) -> list[User]:
    """List users (newest first, paginated). Optional tenant_id, role, is_active; omit is_deleted to include both deleted and non-deleted (admin list)."""
    q = select(User).order_by(User.created_at.desc())
    if is_deleted is not None:
        if is_deleted:
            q = q.where(User.deleted_at.isnot(None))
        else:
            q = q.where(User.deleted_at.is_(None))
    if tenant_id is not None:
        q = q.where(User.tenant_id == tenant_id)
    if role is not None:
        q = q.where(User.role == role)
    if is_active is not None:
        q = q.where(User.is_active.is_(is_active))
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


async def count_users(
    db: AsyncSession,
    tenant_id: UUID | None = None,
    role: UserRole | None = None,
    is_active: bool | None = None,
    is_deleted: bool | None = None,
) -> int:
    """Total count with same filters as get_users (for pagination). Omit is_deleted to count all."""
    q = select(func.count(User.id))
    if is_deleted is not None:
        if is_deleted:
            q = q.where(User.deleted_at.isnot(None))
        else:
            q = q.where(User.deleted_at.is_(None))
    if tenant_id is not None:
        q = q.where(User.tenant_id == tenant_id)
    if role is not None:
        q = q.where(User.role == role)
    if is_active is not None:
        q = q.where(User.is_active.is_(is_active))
    result = await db.execute(q)
    return result.scalar() or 0


async def create_user(db: AsyncSession, **kwargs) -> User:
    """Create a user. Caller supplies tenant_id, email, username, role, password_hash, is_active, etc.; service enforces uniqueness (email/username)."""
    user = User(**kwargs)
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def update_user(
    db: AsyncSession,
    user_id: UUID,
    *,
    include_deleted: bool = False,
    **updates,
) -> User | None:
    """Update user by id. Excludes soft-deleted unless include_deleted=True (restore sets deleted_at/deleted_by to None). Returns None if not found."""
    user = (
        await get_user_include_deleted(db, user_id)
        if include_deleted
        else await get_user(db, user_id)
    )
    if not user:
        return None
    for key, value in updates.items():
        if hasattr(user, key):
            setattr(user, key, value)
    await db.flush()
    await db.refresh(user)
    return user


async def _cascade_soft_delete_user_related(
    db: AsyncSession, user_id: UUID, deleted_by: UUID | None
) -> None:
    """Bulk soft-delete: tasks (owner or assignee), comments, leaves, invitations. Only touches rows where deleted_at is None."""
    now = datetime.now(UTC)
    # Tasks where user is owner or assignee
    await db.execute(
        update(Task)
        .where(
            or_(Task.owner_id == user_id, Task.assignee_id == user_id),
            Task.deleted_at.is_(None),
        )
        .values(deleted_at=now, deleted_by=deleted_by)
    )
    # Comments by user
    await db.execute(
        update(Comment)
        .where(Comment.user_id == user_id, Comment.deleted_at.is_(None))
        .values(deleted_at=now, deleted_by=deleted_by)
    )
    # Leaves requested by user
    await db.execute(
        update(Leave)
        .where(Leave.user_id == user_id, Leave.deleted_at.is_(None))
        .values(deleted_at=now, deleted_by=deleted_by)
    )
    # Invitations created by user
    await db.execute(
        update(Invitation)
        .where(
            Invitation.created_by_id == user_id,
            Invitation.deleted_at.is_(None),
        )
        .values(deleted_at=now, deleted_by=deleted_by)
    )


async def soft_delete_user(
    db: AsyncSession, user_id: UUID, deleted_by: UUID | None = None
) -> bool:
    """Soft-delete user (SoftDeleteMixin) then cascade to related records. Returns True if user existed and was deleted."""
    user = await get_user(db, user_id)
    if not user:
        return False
    user.soft_delete(deleted_by)
    await _cascade_soft_delete_user_related(db, user_id, deleted_by)
    await db.flush()
    return True


async def _cascade_restore_user_related(
    db: AsyncSession, user_id: UUID, deleted_by_id: UUID | None
) -> None:
    """Restore related records that were cascade-deleted with this user. Only restores where deleted_by == deleted_by_id (same admin); does not restore records deleted by the user (deleted_by == user_id)."""
    if deleted_by_id is None:
        return
    # Tasks where user is owner or assignee, and were deleted by the same admin
    await db.execute(
        update(Task)
        .where(
            or_(Task.owner_id == user_id, Task.assignee_id == user_id),
            Task.deleted_by == deleted_by_id,
        )
        .values(deleted_at=None, deleted_by=None)
    )
    await db.execute(
        update(Comment)
        .where(Comment.user_id == user_id, Comment.deleted_by == deleted_by_id)
        .values(deleted_at=None, deleted_by=None)
    )
    await db.execute(
        update(Leave)
        .where(Leave.user_id == user_id, Leave.deleted_by == deleted_by_id)
        .values(deleted_at=None, deleted_by=None)
    )
    await db.execute(
        update(Invitation)
        .where(
            Invitation.created_by_id == user_id,
            Invitation.deleted_by == deleted_by_id,
        )
        .values(deleted_at=None, deleted_by=None)
    )


async def restore_user(db: AsyncSession, user_id: UUID) -> bool:
    """Restore soft-deleted user (User.restore()) then cascade-restore related rows that were deleted by the same admin (deleted_by_id). Returns False if user not found or not deleted."""
    user = await get_user_include_deleted(db, user_id)
    if not user or user.deleted_at is None:
        return False
    deleted_by_id = user.deleted_by  # admin who deleted this user
    user.restore()
    await _cascade_restore_user_related(db, user_id, deleted_by_id)
    await db.flush()
    return True
