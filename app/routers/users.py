"""User routes: me (profile), list/get/create/update/delete users, invite, restore. Role-scoped; tenant_id from JWT."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.messages import USER_CANNOT_UPDATE_SELF, USER_USE_ME_ENDPOINT
from app.database.init_db import get_db
from app.dependencies.permissions import require_roles
from app.dependencies.tenant import get_current_tenant
from app.dependencies.user import get_current_user
from app.enums import UserRole
from app.models import Tenant, User
from app.schemas.invitation import InvitationCreateSchema
from app.schemas.response import MessageResponse
from app.schemas.user import (
    ChangePasswordSchema,
    UserCreateSchema,
    UserMeUpdateSchema,
    UserUpdateSchema,
)
from app.services import invitation_service, user_service

# Routes use get_current_user (tenant_id from JWT). get_current_tenant used only where tenant scope is needed (e.g. invite).
router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me/")
async def get_me(current_user: User = Depends(get_current_user)):
    """Current user profile."""
    return await user_service.get_me(current_user)


@router.patch("/me/")
async def update_me(
    data: UserMeUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update own profile."""
    return await user_service.update_me(db, current_user, data)


@router.delete("/me/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete own account (INTERN or MENTOR only). Tenant Admin and Super Admin cannot delete their accounts."""
    # Block admin self-delete so tenant/platform always has at least one admin.
    if current_user.role in (UserRole.SUPER_ADMIN, UserRole.TENANT_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant Admin and Super Admin accounts cannot be deleted.",
        )
    await user_service.delete_me(db, current_user)


@router.post("/me/change-password/", response_model=MessageResponse)
async def change_password(
    data: ChangePasswordSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change own password."""
    return await user_service.change_password(db, current_user, data)


@router.get("/")
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(10, ge=1, le=100, description="Items per page."),
    is_active: bool | None = Query(
        None, description="Filter by active status. Omit to include all."
    ),
    is_deleted: bool | None = Query(
        None, description="Filter by deleted status. Omit to include all."
    ),
):
    """List users (role-scoped: MENTOR=interns, TENANT_ADMIN=tenant, SUPER_ADMIN=tenant admins). Omit is_active and is_deleted to show all users."""
    skip = (page - 1) * page_size
    limit = page_size
    # INTERN cannot list other users; must use /me for own profile.
    if current_user.role == UserRole.INTERN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action.",
        )
    return await user_service.list_users(
        db,
        current_user,
        skip=skip,
        limit=limit,
        is_active=is_active,
        is_deleted=is_deleted,
    )


@router.get("/{user_id}/")
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get user by ID. Service returns 404 if user not in scope. INTERN must use GET /me/ instead."""
    if current_user.role == UserRole.INTERN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=USER_USE_ME_ENDPOINT,
        )
    return await user_service.get_user_by_id(db, user_id, current_user)


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreateSchema,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create user (TENANT_ADMIN: Mentor/Intern in own tenant; SUPER_ADMIN: any tenant). Service sends verification email."""
    if current_user.role not in (UserRole.TENANT_ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action.",
        )
    return await user_service.create_user(
        db, data, current_user, background_tasks=background_tasks
    )


@router.patch("/{user_id}/")
async def update_user(
    user_id: UUID,
    data: UserUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update user (scope check). Cannot update own profile via this endpoint—use PATCH /me/."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=USER_CANNOT_UPDATE_SELF,
        )
    if current_user.role == UserRole.INTERN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action.",
        )
    return await user_service.update_user(db, user_id, data, current_user)


@router.delete("/{user_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete user. Service enforces not self and tenant scope (404 if user not in scope)."""
    if current_user.role not in (UserRole.TENANT_ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action.",
        )
    await user_service.delete_user(db, user_id, current_user)


@router.post("/invite/", status_code=status.HTTP_201_CREATED)
async def invite_user(
    data: InvitationCreateSchema,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.MENTOR, UserRole.TENANT_ADMIN)),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Invite user (MENTOR or TENANT_ADMIN; invite role INTERN or MENTOR). Tenant from JWT; require_roles blocks INTERN."""
    return await invitation_service.create_invitation(
        db,
        data,
        tenant.id,
        current_user.id,
        background_tasks=background_tasks,
    )


@router.post("/{user_id}/restore/")
async def restore_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Restore soft-deleted user. Service enforces tenant scope (404 if user not in scope or not deleted)."""
    if current_user.role not in (UserRole.TENANT_ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action.",
        )
    return await user_service.restore_user(db, user_id, current_user)
