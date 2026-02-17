"""User service: me, list, get, create, update, delete, restore, change-password. Role and tenant scoped; list/get/update/delete use _can_access_user and _user_scope_for_list."""

from uuid import UUID

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import user_crud
from app.dependencies.tenant import verify_tenant_access
from app.enums import UserRole
from app.models import User
from app.schemas.user import (
    ChangePasswordSchema,
    UserCreateSchema,
    UserMeUpdateSchema,
    UserResponseSchema,
    UserUpdateSchema,
)
from app.services.email_service import email_service
from app.utils.otp_handler import send_otp
from app.utils.password import hash_password, verify_password
from app.utils.response_helpers import success_list_response, success_response


def _user_to_list_item(user: User) -> dict:
    """User dict for list: flat tenant_id (no nested tenant object), same fields as UserResponseSchema."""
    data = UserResponseSchema.model_validate(user).model_dump(mode="json")
    data.pop("tenant", None)
    return {
        "id": data["id"],
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
        "username": data["username"],
        "email": data["email"],
        "first_name": data["first_name"],
        "last_name": data["last_name"],
        "role": data["role"],
        "is_verified": data["is_verified"],
        "is_active": data["is_active"],
        "created_at": data["created_at"],
        "updated_at": data["updated_at"],
        "deleted_at": data["deleted_at"],
    }


def _can_access_user(current_user: User, target_user: User) -> bool:
    """True if current_user can view/update/delete target_user. SUPER_ADMIN: only TENANT_ADMIN users; TENANT_ADMIN: same tenant; MENTOR: same tenant + INTERN only; INTERN: only self."""
    if current_user.id == target_user.id:
        return True
    if current_user.role == UserRole.SUPER_ADMIN:
        return target_user.role == UserRole.TENANT_ADMIN
    if current_user.role == UserRole.TENANT_ADMIN:
        return (
            current_user.tenant_id is not None
            and target_user.tenant_id == current_user.tenant_id
        )
    if current_user.role == UserRole.MENTOR:
        return (
            current_user.tenant_id is not None
            and target_user.tenant_id == current_user.tenant_id
            and target_user.role == UserRole.INTERN
        )
    if current_user.role == UserRole.INTERN:
        return current_user.id == target_user.id
    return False


def _user_scope_for_list(current_user: User) -> tuple[UUID | None, UserRole | None]:
    """Return (tenant_id, role_filter) for list_users. SUPER_ADMIN: tenant_id=None, role=TENANT_ADMIN; TENANT_ADMIN: own tenant, all roles; MENTOR: own tenant, INTERN only; INTERN: router blocks list."""
    if current_user.role == UserRole.SUPER_ADMIN:
        return (None, UserRole.TENANT_ADMIN)
    if current_user.role == UserRole.TENANT_ADMIN:
        return (current_user.tenant_id, None)
    if current_user.role == UserRole.MENTOR:
        return (current_user.tenant_id, UserRole.INTERN)
    return (current_user.tenant_id, UserRole.INTERN)


async def get_me(current_user: User) -> dict:
    """Current user profile."""
    return success_response(
        UserResponseSchema.model_validate(current_user).model_dump(mode="json")
    )


async def update_me(
    db: AsyncSession, current_user: User, data: UserMeUpdateSchema
) -> dict:
    """Update own profile."""
    updates = {}
    if data.first_name is not None:
        updates["first_name"] = data.first_name.strip()
    if data.last_name is not None:
        updates["last_name"] = data.last_name.strip()
    if updates:
        await user_crud.update_user(db, current_user.id, **updates)
    await db.commit()
    await db.refresh(current_user)
    return await get_me(current_user)


async def delete_me(db: AsyncSession, current_user: User) -> None:
    """Soft-delete own account (INTERN/MENTOR only; router blocks admin). deleted_by=self so auth allows re-registration with same email."""
    await user_crud.soft_delete_user(db, current_user.id, deleted_by=current_user.id)
    await db.commit()


async def change_password(
    db: AsyncSession, current_user: User, data: ChangePasswordSchema
) -> dict:
    """Change own password. Verify old password before updating."""
    if not verify_password(data.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    await user_crud.update_user(
        db, current_user.id, hashed_password=hash_password(data.new_password)
    )
    await db.commit()
    return success_response({}, "Password updated")


async def list_users(
    db: AsyncSession,
    current_user: User,
    skip: int = 0,
    limit: int = 10,
    is_active: bool | None = None,
    is_deleted: bool | None = None,
) -> dict:
    """List users (role-scoped via _user_scope_for_list). Omit is_active/is_deleted to show all."""
    tenant_id, role = _user_scope_for_list(current_user)
    users = await user_crud.get_users(
        db,
        skip=skip,
        limit=limit,
        tenant_id=tenant_id,
        role=role,
        is_active=is_active,
        is_deleted=is_deleted,
    )
    total = await user_crud.count_users(
        db,
        tenant_id=tenant_id,
        role=role,
        is_active=is_active,
        is_deleted=is_deleted,
    )
    data = [_user_to_list_item(u) for u in users]
    return success_list_response(data, skip=skip, limit=limit, total=total)


async def get_user_by_id(db: AsyncSession, user_id: UUID, current_user: User) -> dict:
    """Get user by id. 404 if not found or _can_access_user false (don't leak existence)."""
    user = await user_crud.get_user(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    if not _can_access_user(current_user, user):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return success_response(
        UserResponseSchema.model_validate(user).model_dump(mode="json")
    )


async def create_user(
    db: AsyncSession,
    data: UserCreateSchema,
    current_user: User,
    background_tasks: BackgroundTasks | None = None,
) -> dict:
    """Create user. TENANT_ADMIN: tenant from JWT, role MENTOR/INTERN. SUPER_ADMIN: tenant_id in body, role TENANT_ADMIN only. Email/username unique within tenant. Sends verify OTP after commit."""
    if current_user.role == UserRole.SUPER_ADMIN:
        if data.role != UserRole.TENANT_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Super admin can only create tenant admins",
            )
        if not data.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tenant_id required when creating tenant admin",
            )
        tenant_id = data.tenant_id
    else:
        if current_user.tenant_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tenant context",
            )
        tenant_id = current_user.tenant_id
        if data.role not in (UserRole.MENTOR, UserRole.INTERN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Can only create Mentor or Intern",
            )
        if data.tenant_id is not None and data.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot create user in another tenant",
            )

    # Email and username unique within tenant (not globally; same email can exist in another tenant).
    existing_email = await user_crud.get_user_by_email_ci(db, data.email, tenant_id)
    existing_username = await user_crud.get_user_by_username_ci(
        db, data.username, tenant_id
    )
    if existing_email and existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email and username already exist",
        )
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered in this organization",
        )
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken",
        )

    user = await user_crud.create_user(
        db,
        tenant_id=tenant_id,
        username=data.username.strip(),
        email=data.email.lower().strip(),
        first_name=data.first_name.strip(),
        last_name=data.last_name.strip(),
        hashed_password=hash_password(data.password),
        role=data.role,
        is_verified=False,
        is_active=False,
    )
    await db.commit()
    await db.refresh(user)

    if background_tasks:
        async def _send(email: str, subj: str, body: str) -> None:
            await email_service.send_email(email, subj, body)

        # OTP key uses tenant_id so verify_email flow can look up user by email (same tenant).
        await send_otp(
            user.email,
            "verify_email",
            tenant_id,
            _send,
            subject="Verify your email",
            body_template="Your verification OTP is: {otp}. It expires in {minutes} minutes.",
            background_tasks=background_tasks,
        )

    return success_response(
        UserResponseSchema.model_validate(user).model_dump(mode="json"),
        "User created successfully. A verification email has been sent to the user.",
    )


async def update_user(
    db: AsyncSession, user_id: UUID, data: UserUpdateSchema, current_user: User
) -> dict:
    """Update user. Only first_name, last_name, is_active; scope via _can_access_user. Router blocks self-update (use PATCH /me/)."""
    user = await user_crud.get_user(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    if not _can_access_user(current_user, user):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    updates = {}
    if data.first_name is not None:
        updates["first_name"] = data.first_name.strip()
    if data.last_name is not None:
        updates["last_name"] = data.last_name.strip()
    if data.is_active is not None:
        updates["is_active"] = data.is_active
    if updates:
        await user_crud.update_user(db, user_id, **updates)
    await db.commit()
    await db.refresh(user)
    return await get_user_by_id(db, user_id, current_user)


async def delete_user(db: AsyncSession, user_id: UUID, current_user: User) -> None:
    """Soft-delete user (deleted_at/deleted_by). Reject self; use DELETE /me/ for own account. Scope via _can_access_user."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete own account here; use DELETE /users/me/",
        )
    user = await user_crud.get_user(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    if not _can_access_user(current_user, user):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    await user_crud.soft_delete_user(db, user_id, deleted_by=current_user.id)
    await db.commit()


async def restore_user(db: AsyncSession, user_id: UUID, current_user: User) -> dict:
    """Restore soft-deleted user. Must fetch with include_deleted; reject if user not deleted. Scope via _can_access_user."""
    user = await user_crud.get_user_include_deleted(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    if user.deleted_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not deleted",
        )
    if not _can_access_user(current_user, user):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    await user_crud.restore_user(db, user_id)
    await db.commit()
    await db.refresh(user)
    return await get_user_by_id(db, user_id, current_user)
