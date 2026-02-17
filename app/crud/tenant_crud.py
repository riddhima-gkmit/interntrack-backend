"""Tenant CRUD: get, get by name, list, count, create, update, soft-delete. No tenant scope (tenants are top-level); used for tenant admin and auth (e.g. resolving tenant from JWT)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Tenant


async def get_tenant(
    db: AsyncSession, tenant_id: UUID, include_deleted: bool = False
) -> Tenant | None:
    """Get tenant by id. Excludes soft-deleted unless include_deleted (e.g. for admin or audit)."""
    q = select(Tenant).where(Tenant.id == tenant_id)
    if not include_deleted:
        q = q.where(Tenant.deleted_at.is_(None))
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def get_tenant_by_name(
    db: AsyncSession, name: str, include_deleted: bool = False
) -> Tenant | None:
    """Get tenant by name (for uniqueness check or lookup). Caller should pass trimmed name; excludes soft-deleted unless include_deleted."""
    q = select(Tenant).where(Tenant.name == name)
    if not include_deleted:
        q = q.where(Tenant.deleted_at.is_(None))
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def get_tenants(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 10,
    is_active: bool | None = None,
    include_deleted: bool = False,
    only_deleted: bool = False,
) -> list[Tenant]:
    """List tenants (newest first, paginated). only_deleted=True returns only soft-deleted; otherwise optional is_active and include_deleted."""
    q = select(Tenant).order_by(Tenant.created_at.desc())
    if only_deleted:
        q = q.where(Tenant.deleted_at.isnot(None))
    elif not include_deleted:
        q = q.where(Tenant.deleted_at.is_(None))
    if is_active is not None and not only_deleted:
        q = q.where(Tenant.is_active.is_(is_active))
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


async def count_tenants(
    db: AsyncSession,
    is_active: bool | None = None,
    include_deleted: bool = False,
    only_deleted: bool = False,
) -> int:
    """Total count with same filters as get_tenants. only_deleted=True counts only soft-deleted tenants."""
    from sqlalchemy import func

    q = select(func.count(Tenant.id))
    if only_deleted:
        q = q.where(Tenant.deleted_at.isnot(None))
    else:
        if not include_deleted:
            q = q.where(Tenant.deleted_at.is_(None))
        if is_active is not None:
            q = q.where(Tenant.is_active.is_(is_active))
    result = await db.execute(q)
    return result.scalar() or 0


async def create_tenant(
    db: AsyncSession, *, name: str, is_active: bool = True
) -> Tenant:
    """Create a tenant. Name is stripped; is_active defaults to True. Service should check get_tenant_by_name for uniqueness."""
    tenant = Tenant(name=name.strip(), is_active=is_active)
    db.add(tenant)
    await db.flush()
    await db.refresh(tenant)
    return tenant


async def update_tenant(db: AsyncSession, tenant_id: UUID, **updates) -> Tenant | None:
    """Update tenant by id. Uses get_tenant so soft-deleted are skipped; only applies updates where value is not None. Returns None if not found."""
    tenant = await get_tenant(db, tenant_id)
    if not tenant:
        return None
    for key, value in updates.items():
        if hasattr(tenant, key) and value is not None:
            setattr(tenant, key, value)
    await db.flush()
    await db.refresh(tenant)
    return tenant


async def soft_delete_tenant(
    db: AsyncSession, tenant_id: UUID, deleted_by: UUID | None = None
) -> bool:
    """Soft-delete tenant (SoftDeleteMixin). Returns True if tenant existed and was deleted."""
    tenant = await get_tenant(db, tenant_id)
    if not tenant:
        return False
    tenant.soft_delete(deleted_by)
    await db.flush()
    return True
