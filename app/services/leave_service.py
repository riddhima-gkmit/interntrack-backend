"""Leave service: list/get/create/update/delete with role and tenant scope. Overlapping leave for same user is rejected. Uses verify_tenant_access + _can_access_leave."""

from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import leave_crud, user_crud
from app.dependencies.tenant import verify_tenant_access
from app.enums import LeaveStatus, LeaveType, UserRole
from app.models import Leave, User
from app.schemas.tenant import TenantResponseSchema
from app.schemas.user import UserResponseSchema
from app.utils.response_helpers import success_list_response, success_response


def _leave_to_response(leave: Leave) -> dict:
    """Flat leave payload for list/create/update (ids, no nested tenant/user)."""
    return {
        "id": str(leave.id),
        "tenant_id": str(leave.tenant_id),
        "user_id": str(leave.user_id),
        "leave_type": leave.leave_type.value,
        "start_date": leave.start_date.isoformat(),
        "end_date": leave.end_date.isoformat(),
        "status": leave.status.value,
        "approved_by": str(leave.approved_by) if leave.approved_by else None,
        "reason": leave.reason,
        "created_at": leave.created_at.isoformat(),
        "updated_at": leave.updated_at.isoformat(),
        "deleted_at": leave.deleted_at.isoformat() if leave.deleted_at else None,
    }


def _user_to_embed_dict(user: User) -> dict:
    """User dict for embedding in other responses: same as UserResponseSchema but tenant_id only (no tenant object)."""
    data = UserResponseSchema.model_validate(user).model_dump(mode="json")
    data.pop("tenant", None)
    data["tenant_id"] = str(user.tenant_id) if user.tenant_id else None
    return data


def _leave_to_detail_response(leave: Leave) -> dict:
    """Leave response with tenant, user, and approved_by as full objects (no tenant_id/user_id). User/approved_by have tenant_id only, not tenant object."""
    return {
        "id": str(leave.id),
        "tenant": (
            TenantResponseSchema.model_validate(leave.tenant).model_dump(mode="json")
            if leave.tenant
            else None
        ),
        "user": _user_to_embed_dict(leave.user) if leave.user else None,
        "leave_type": leave.leave_type.value,
        "start_date": leave.start_date.isoformat(),
        "end_date": leave.end_date.isoformat(),
        "status": leave.status.value,
        "approved_by": (
            _user_to_embed_dict(leave.approver) if leave.approver else None
        ),
        "reason": leave.reason,
        "created_at": leave.created_at.isoformat(),
        "updated_at": leave.updated_at.isoformat(),
        "deleted_at": leave.deleted_at.isoformat() if leave.deleted_at else None,
    }


def _can_access_leave_sync(current_user: User, leave: Leave) -> bool:
    """Sync check: tenant and own leave. For MENTOR non-own, use _can_access_leave."""
    if current_user.tenant_id is None:
        return False
    if leave.tenant_id != current_user.tenant_id:
        return False
    if current_user.role == UserRole.TENANT_ADMIN:
        return True
    if current_user.role in (UserRole.INTERN, UserRole.MENTOR):
        return leave.user_id == current_user.id
    return False


async def _can_access_leave(db: AsyncSession, current_user: User, leave: Leave) -> bool:
    """True if current_user can view this leave. MENTOR: own leave or leave's user is INTERN only (cannot see other mentors' leaves)."""
    if _can_access_leave_sync(current_user, leave):
        return True
    if current_user.role == UserRole.MENTOR and leave.user_id != current_user.id:
        leave_user = await user_crud.get_user(db, leave.user_id)
        return leave_user is not None and leave_user.role == UserRole.INTERN
    return False


async def _get_mentor_leave_user_ids(
    db: AsyncSession, tenant_id: UUID, current_user_id: UUID
) -> list[UUID]:
    """User IDs for MENTOR: self + all interns in tenant. Other mentors are excluded so mentors cannot see other mentors' leaves."""
    interns = await user_crud.get_users(
        db, skip=0, limit=5000, tenant_id=tenant_id, role=UserRole.INTERN
    )
    ids = [current_user_id]
    for u in interns:
        ids.append(u.id)
    return ids


async def list_leaves(
    db: AsyncSession,
    current_user: User,
    tenant_id: UUID,
    skip: int = 0,
    limit: int = 10,
    status: LeaveStatus | None = None,
    leave_type: LeaveType | None = None,
    user_id: UUID | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    """List leaves. INTERN: own only. MENTOR: own + all interns (cannot see other mentors' leaves). TENANT_ADMIN: all tenant."""
    # INTERN: force filter to self. MENTOR: user_ids = self + interns (crud filters by this list). TENANT_ADMIN: no user_ids filter.
    if current_user.role == UserRole.INTERN:
        user_ids = None
        filter_user_id = user_id or current_user.id
    elif current_user.role == UserRole.MENTOR:
        user_ids = await _get_mentor_leave_user_ids(db, tenant_id, current_user.id)
        filter_user_id = user_id
    else:
        user_ids = None
        filter_user_id = user_id

    leaves = await leave_crud.get_leaves(
        db,
        tenant_id=tenant_id,
        skip=skip,
        limit=limit,
        status=status,
        leave_type=leave_type,
        user_id=filter_user_id,
        user_ids=user_ids,
        start_date=start_date,
        end_date=end_date,
    )
    total = await leave_crud.count_leaves(
        db,
        tenant_id=tenant_id,
        status=status,
        leave_type=leave_type,
        user_id=filter_user_id,
        user_ids=user_ids,
        start_date=start_date,
        end_date=end_date,
    )
    data = [_leave_to_response(l) for l in leaves]
    return success_list_response(data, skip=skip, limit=limit, total=total)


async def get_leave_by_id(
    db: AsyncSession, leave_id: UUID, current_user: User, tenant_id: UUID
) -> dict:
    """Get leave by id (scope check). MENTOR: only own leave or interns' leaves (not other mentors'). Returns full tenant, user, and approved_by objects."""
    leave = await leave_crud.get_leave_with_details(db, leave_id, tenant_id=tenant_id)
    if not leave:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Leave not found"
        )
    verify_tenant_access(current_user, leave.tenant_id)
    if not await _can_access_leave(db, current_user, leave):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Leave not found"
        )
    return success_response(_leave_to_detail_response(leave))


async def create_leave(
    db: AsyncSession,
    leave_type: LeaveType,
    start_date: datetime,
    end_date: datetime,
    reason: str | None,
    current_user: User,
    tenant_id: UUID,
    user_id: UUID | None = None,
) -> dict:
    """
    Create leave. If user_id provided: TENANT_ADMIN only, for INTERN/MENTOR in same tenant (status=approved).
    Otherwise: leave for current_user; if current_user is TENANT_ADMIN then status=approved, else PENDING.
    """
    if end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be on or after start_date",
        )

    target_user_id: UUID
    is_created_by_tenant_admin: bool = current_user.role == UserRole.TENANT_ADMIN

    if current_user.role == UserRole.TENANT_ADMIN:
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="user_id is required when tenant admin creates leave. Specify an intern or mentor.",
            )
        target_user = await user_crud.get_user(db, user_id)
        if not target_user or target_user.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found in this tenant.",
            )
        if target_user.role not in (UserRole.INTERN, UserRole.MENTOR):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Leave can only be created for an intern or mentor.",
            )
        if target_user.id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tenant admin cannot create leave for themselves. Specify user_id for an intern or mentor.",
            )
        target_user_id = user_id
    elif user_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only tenant admin can create leave for another user.",
        )
    else:
        target_user_id = current_user.id

    # Reject if target user already has leave overlapping [start_date, end_date].
    overlapping = await leave_crud.has_overlapping_leave(
        db, tenant_id, target_user_id, start_date, end_date
    )
    if overlapping:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has leave for the same or overlapping dates. Cannot create duplicate leave.",
        )

    # TENANT_ADMIN-created leave is auto-approved; INTERN/MENTOR self-request is PENDING.
    status_value = (
        LeaveStatus.APPROVED if is_created_by_tenant_admin else LeaveStatus.PENDING
    )
    approved_by = current_user.id if status_value == LeaveStatus.APPROVED else None

    leave = await leave_crud.create_leave(
        db,
        tenant_id=tenant_id,
        user_id=target_user_id,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        reason=reason.strip() if reason else None,
        status=status_value,
        approved_by=approved_by,
    )
    await db.commit()
    await db.refresh(leave)
    return success_response(_leave_to_response(leave))


async def update_leave(
    db: AsyncSession,
    leave_id: UUID,
    current_user: User,
    tenant_id: UUID,
    new_status: LeaveStatus | None = None,
    leave_type: LeaveType | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    """
    Update leave: all fields optional (null). Only provided fields are updated.
    end_date must be on or after start_date when both given.
    """
    leave = await leave_crud.get_leave(db, leave_id, tenant_id=tenant_id)
    if not leave:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Leave not found"
        )
    verify_tenant_access(current_user, leave.tenant_id)
    if not await _can_access_leave(db, current_user, leave):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Leave not found"
        )

    # Validate end >= start using provided values or existing leave dates.
    effective_start = start_date if start_date is not None else leave.start_date
    effective_end = end_date if end_date is not None else leave.end_date
    if effective_end < effective_start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be on or after start_date",
        )

    updates: dict = {}
    if start_date is not None:
        updates["start_date"] = start_date
    if end_date is not None:
        updates["end_date"] = end_date
    if leave_type is not None:
        updates["leave_type"] = leave_type

    if new_status is not None:
        # CANCELLED: only PENDING; INTERN can only cancel own. APPROVED/REJECTED: only MENTOR/TENANT_ADMIN, only PENDING; MENTOR cannot approve own or non-intern.
        if new_status == LeaveStatus.CANCELLED:
            if leave.status != LeaveStatus.PENDING:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Only PENDING leave can be cancelled",
                )
            if (
                current_user.role == UserRole.INTERN
                and leave.user_id != current_user.id
            ):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Leave not found"
                )
            updates["status"] = LeaveStatus.CANCELLED
        elif new_status in (LeaveStatus.APPROVED, LeaveStatus.REJECTED):
            if current_user.role == UserRole.INTERN:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Interns cannot approve or reject leave requests. Only mentors or tenant admins can.",
                )
            if leave.status != LeaveStatus.PENDING:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Only PENDING leave can be approved or rejected",
                )
            if current_user.role == UserRole.MENTOR:
                leave_user = await user_crud.get_user(db, leave.user_id)
                if not leave_user:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND, detail="Leave not found"
                    )
                if leave.user_id == current_user.id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You cannot approve or reject your own leave. Only another mentor or tenant admin can approve it.",
                    )
                if leave_user.role != UserRole.INTERN:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Mentors can only approve or reject leave requests for interns.",
                    )
            updates["status"] = new_status
            updates["approved_by"] = current_user.id
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only CANCELLED, APPROVED, or REJECTED allowed",
            )

    await leave_crud.update_leave(db, leave_id, **updates)
    await db.commit()
    await db.refresh(leave)
    return success_response(_leave_to_response(leave))


async def delete_leave(
    db: AsyncSession, leave_id: UUID, current_user: User, tenant_id: UUID
) -> None:
    """Soft-delete leave. Only TENANT_ADMIN; sets deleted_at/deleted_by."""
    if current_user.role != UserRole.TENANT_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only tenant admin can permanently delete leave records.",
        )
    leave = await leave_crud.get_leave(db, leave_id, tenant_id=tenant_id)
    if not leave:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Leave not found"
        )
    verify_tenant_access(current_user, leave.tenant_id)
    await leave_crud.soft_delete_leave(
        db, leave_id, tenant_id=leave.tenant_id, deleted_by=current_user.id
    )
    await db.commit()
