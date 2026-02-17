"""Tenant service: register (self + create tenant admin), list/get/create/update/delete. get/update/delete use verify_tenant_access for scope (TENANT_ADMIN own only, SUPER_ADMIN any)."""

from uuid import UUID

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import tenant_crud, user_crud
from app.dependencies.tenant import verify_tenant_access
from app.enums import UserRole
from app.models import User
from app.schemas.tenant import (
    TenantCreateSchema,
    TenantRegisterSchema,
    TenantResponseSchema,
    TenantUpdateSchema,
)
from app.services.email_service import email_service
from app.utils.otp_handler import send_otp
from app.utils.password import hash_password
from app.utils.response_helpers import success_list_response, success_response


async def register_tenant(
    db: AsyncSession,
    data: TenantRegisterSchema,
    background_tasks: BackgroundTasks | None = None,
) -> dict:
    """Tenant self-registration: create tenant + first user as TENANT_ADMIN, send verify OTP. No auth. Reject if tenant name or email/username (any tenant) exists."""
    existing_tenant = await tenant_crud.get_tenant_by_name(db, data.name.strip())
    if existing_tenant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant name already exists",
        )
    # Email and username are globally unique (across tenants) for self-registration.
    existing_email = await user_crud.get_user_by_email_any_tenant(db, data.email)
    existing_username = await user_crud.get_user_by_username_any_tenant(
        db, data.username.strip()
    )
    if existing_email and existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email and username already exist",
        )
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists",
        )
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )
    tenant = await tenant_crud.create_tenant(db, name=data.name.strip())
    await db.flush()
    first_name = (data.first_name or data.username).strip()
    last_name = (data.last_name or "").strip()
    user = await user_crud.create_user(
        db,
        tenant_id=tenant.id,
        username=data.username.strip(),
        email=data.email.lower().strip(),
        first_name=first_name,
        last_name=last_name,
        hashed_password=hash_password(data.password),
        role=UserRole.TENANT_ADMIN,
        is_verified=False,
        is_active=False,
    )
    await db.flush()

    async def _send(email: str, subj: str, body: str) -> None:
        await email_service.send_email(email, subj, body)

    await db.commit()
    # OTP key uses tenant.id so verify_email can resolve tenant from user after they verify.
    await send_otp(
        data.email.lower().strip(),
        "verify_email",
        tenant.id,
        _send,
        subject="Verify your email",
        body_template="Your verification OTP is: {otp}. It expires in {minutes} minutes.",
        background_tasks=background_tasks,
    )
    return {
        "success": True,
        "message": "Registration successful. Please verify your email.",
    }


async def create_tenant(db: AsyncSession, data: TenantCreateSchema) -> dict:
    """Create tenant (SUPER_ADMIN only). Reject if name already exists."""
    existing = await tenant_crud.get_tenant_by_name(db, data.name.strip())
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant name already exists",
        )
    tenant = await tenant_crud.create_tenant(db, name=data.name.strip())
    await db.commit()
    await db.refresh(tenant)
    return success_response(
        TenantResponseSchema.model_validate(tenant).model_dump(mode="json")
    )


async def list_tenants(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 10,
    is_active: bool | None = None,
) -> dict:
    """List tenants with pagination (SUPER_ADMIN only)."""
    tenants = await tenant_crud.get_tenants(
        db, skip=skip, limit=limit, is_active=is_active
    )
    total = await tenant_crud.count_tenants(db, is_active=is_active)
    data = [
        TenantResponseSchema.model_validate(t).model_dump(mode="json") for t in tenants
    ]
    return success_list_response(data, skip=skip, limit=limit, total=total)


async def get_tenant(db: AsyncSession, tenant_id: UUID, current_user: User) -> dict:
    """Get tenant by id. verify_tenant_access: TENANT_ADMIN gets 404 if tenant_id != own; SUPER_ADMIN can access any."""
    verify_tenant_access(current_user, tenant_id)
    tenant = await tenant_crud.get_tenant(db, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return success_response(
        TenantResponseSchema.model_validate(tenant).model_dump(mode="json")
    )


async def update_tenant(
    db: AsyncSession,
    tenant_id: UUID,
    data: TenantUpdateSchema,
    current_user: User,
) -> dict:
    """Update tenant. TENANT_ADMIN: own only; SUPER_ADMIN: any."""
    verify_tenant_access(current_user, tenant_id)
    tenant = await tenant_crud.get_tenant(db, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    updates = {}
    if data.name is not None:
        # Name must be unique; allow same tenant to keep current name (existing.id == tenant_id).
        existing = await tenant_crud.get_tenant_by_name(db, data.name.strip())
        if existing and existing.id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tenant name already exists",
            )
        updates["name"] = data.name.strip()
    if data.is_active is not None:
        updates["is_active"] = data.is_active
    if updates:
        updated = await tenant_crud.update_tenant(db, tenant_id, **updates)
        if updated:
            tenant = updated
    await db.commit()
    await db.refresh(tenant)
    return success_response(
        TenantResponseSchema.model_validate(tenant).model_dump(mode="json")
    )


async def delete_tenant(
    db: AsyncSession,
    tenant_id: UUID,
    current_user: User,
    deleted_by: UUID | None = None,
) -> None:
    """Soft-delete tenant (deleted_at/deleted_by). Reject if tenant has any active users (is_active=True). Scope: verify_tenant_access."""
    verify_tenant_access(current_user, tenant_id)
    tenant = await tenant_crud.get_tenant(db, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    active_count = await user_crud.count_active_users_by_tenant(db, tenant_id)
    if active_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete tenant with active users",
        )
    await tenant_crud.soft_delete_tenant(
        db, tenant_id, deleted_by=deleted_by or current_user.id
    )
    await db.commit()
