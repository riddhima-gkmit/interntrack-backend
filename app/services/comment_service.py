"""Comment service: list/get/create/update/delete under a task. Access follows task scope; INTERN can edit/delete only own comments. Uses verify_tenant_access + _can_access_task_for_comment."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.messages import (
    INTERN_CAN_ONLY_DELETE_OWN_COMMENT,
    INTERN_CAN_ONLY_UPDATE_OWN_COMMENT,
)
from app.crud import comment_crud, task_crud
from app.dependencies.tenant import verify_tenant_access
from app.enums import UserRole
from app.models import Comment, Task, User
from app.schemas.tenant import TenantResponseSchema
from app.schemas.user import UserResponseSchema
from app.services.task_service import _can_access_task, _task_to_response
from app.utils.response_helpers import success_list_response, success_response


def _can_access_task_for_comment(current_user: User, task: Task) -> bool:
    """True if current_user can view/add comments. Same as task access, or MENTOR and task is assigned to an INTERN in same tenant."""
    if _can_access_task(current_user, task):
        return True
    if (
        current_user.role == UserRole.MENTOR
        and task.tenant_id == current_user.tenant_id
        and task.assignee_id
    ):
        assignee = task.assignee
        return assignee is not None and assignee.role == UserRole.INTERN
    return False


def _can_edit_delete_comment(current_user: User, comment: Comment) -> bool:
    """True if current_user can update/delete this comment. TENANT_ADMIN/MENTOR: any; INTERN: only own (comment.user_id == self)."""
    if current_user.role in (UserRole.TENANT_ADMIN, UserRole.MENTOR):
        return True
    if current_user.role == UserRole.INTERN:
        return comment.user_id == current_user.id
    return False


def _comment_to_response(comment: Comment) -> dict:
    """Flat comment payload for list/create/update (ids and message, no nested tenant/task/user)."""
    return {
        "id": str(comment.id),
        "tenant_id": str(comment.tenant_id),
        "task_id": str(comment.task_id),
        "user_id": str(comment.user_id),
        "message": comment.message,
        "created_at": comment.created_at.isoformat(),
        "updated_at": comment.updated_at.isoformat(),
        "deleted_at": comment.deleted_at.isoformat() if comment.deleted_at else None,
    }


def _user_for_comment(user) -> dict | None:
    """User dict for embedding in comment response. Pop nested tenant to avoid duplication; include flat tenant_id."""
    if not user:
        return None
    data = UserResponseSchema.model_validate(user).model_dump(mode="json")
    data.pop("tenant", None)
    tenant_id = str(user.tenant_id) if user.tenant_id else None
    return {
        "id": data["id"],
        "tenant_id": tenant_id,
        **{k: v for k, v in data.items() if k != "id"},
    }


def _task_to_response_without_nested(task) -> dict | None:
    """Task dict for embedding in comment detail; strip tenant/owner/assignee to avoid deep nesting."""
    if not task:
        return None
    data = _task_to_response(task)
    for key in ("tenant", "owner", "assignee"):
        data.pop(key, None)
    return data


def _comment_to_full_response(comment: Comment) -> dict:
    """Comment response with full tenant, task (no nested tenant/owner/assignee), and user objects."""
    tenant_data = (
        TenantResponseSchema.model_validate(comment.tenant).model_dump(mode="json")
        if comment.tenant
        else None
    )
    task_data = _task_to_response_without_nested(comment.task)
    user_data = _user_for_comment(comment.user)
    return {
        "id": str(comment.id),
        "tenant": tenant_data,
        "task": task_data,
        "user": user_data,
        "message": comment.message,
        "created_at": comment.created_at.isoformat(),
        "updated_at": comment.updated_at.isoformat(),
        "deleted_at": comment.deleted_at.isoformat() if comment.deleted_at else None,
    }


async def list_comments(
    db: AsyncSession,
    task_id: UUID,
    current_user: User,
    skip: int = 0,
    limit: int = 20,
) -> dict:
    """List comments for a task. 404 if task missing or user has no access (tenant first, then task-level)."""
    task = await task_crud.get_task(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    verify_tenant_access(current_user, task.tenant_id)
    if not _can_access_task_for_comment(current_user, task):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    comments = await comment_crud.get_comments_by_task(
        db, task_id, tenant_id=task.tenant_id, skip=skip, limit=limit
    )
    data = [_comment_to_response(c) for c in comments]
    # Crud returns page only; total = len(data) for this page (no separate count query).
    total = len(data)
    return success_list_response(data, skip=skip, limit=limit, total=total)


async def get_comment_by_id(
    db: AsyncSession,
    task_id: UUID,
    comment_id: UUID,
    current_user: User,
) -> dict:
    """Get comment by id. Returns full comment with tenant, task (no nested owner/assignee), user. 404 if task or comment out of scope."""
    task = await task_crud.get_task(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    verify_tenant_access(current_user, task.tenant_id)
    if not _can_access_task_for_comment(current_user, task):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    comment = await comment_crud.get_comment_with_details(
        db, comment_id, task_id=task_id, tenant_id=task.tenant_id
    )
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )
    return success_response(_comment_to_full_response(comment))


async def create_comment(
    db: AsyncSession,
    task_id: UUID,
    message: str,
    current_user: User,
) -> dict:
    """Create comment on task. Author is current_user; scope = must be able to access task."""
    task = await task_crud.get_task(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    verify_tenant_access(current_user, task.tenant_id)
    if not _can_access_task_for_comment(current_user, task):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    comment = await comment_crud.create_comment(
        db,
        tenant_id=task.tenant_id,
        task_id=task_id,
        user_id=current_user.id,
        message=message.strip(),
    )
    await db.commit()
    await db.refresh(comment)
    return success_response(_comment_to_response(comment))


async def update_comment(
    db: AsyncSession,
    task_id: UUID,
    comment_id: UUID,
    message: str,
    current_user: User,
) -> dict:
    """Update comment. INTERN only if comment.user_id == current_user."""
    task = await task_crud.get_task(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    verify_tenant_access(current_user, task.tenant_id)
    if not _can_access_task_for_comment(current_user, task):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    comment = await comment_crud.get_comment(
        db, comment_id, task_id=task_id, tenant_id=task.tenant_id
    )
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )
    if not _can_edit_delete_comment(current_user, comment):
        # INTERN: 403 with own-comment message; others (e.g. SUPER_ADMIN wrong tenant): 404.
        if current_user.role == UserRole.INTERN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=INTERN_CAN_ONLY_UPDATE_OWN_COMMENT,
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )
    await comment_crud.update_comment(db, comment_id, message=message.strip())
    await db.commit()
    await db.refresh(comment)
    return success_response(_comment_to_response(comment))


async def delete_comment(
    db: AsyncSession,
    task_id: UUID,
    comment_id: UUID,
    current_user: User,
) -> None:
    """Soft-delete comment. INTERN only if comment.user_id == current_user."""
    task = await task_crud.get_task(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    verify_tenant_access(current_user, task.tenant_id)
    if not _can_access_task_for_comment(current_user, task):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    comment = await comment_crud.get_comment(
        db, comment_id, task_id=task_id, tenant_id=task.tenant_id
    )
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )
    if not _can_edit_delete_comment(current_user, comment):
        # INTERN: 403; others: 404 so we don't leak existence.
        if current_user.role == UserRole.INTERN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=INTERN_CAN_ONLY_DELETE_OWN_COMMENT,
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )
    await comment_crud.soft_delete_comment(db, comment_id, deleted_by=current_user.id)
    await db.commit()
