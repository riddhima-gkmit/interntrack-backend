"""Task service: list/get/create/update/delete and history. Enforces assignee rules and unique (owner, assignee, title). Uses verify_tenant_access + _can_access_task."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import task_crud, task_history_crud, user_crud
from app.dependencies.tenant import verify_tenant_access
from app.enums import TaskPriority, TaskStatus, UserRole
from app.models import Task, User
from app.schemas.task import TaskCreateSchema, TaskUpdateSchema
from app.schemas.tenant import TenantResponseSchema
from app.schemas.user import UserResponseSchema
from app.utils.response_helpers import success_list_response, success_response


def _can_access_task(current_user: User, task: Task) -> bool:
    """True if current_user can access this task. TENANT_ADMIN: any in tenant; MENTOR/INTERN: assignee or owner == self."""
    if current_user.tenant_id is None:
        return False
    if task.tenant_id != current_user.tenant_id:
        return False
    if current_user.role == UserRole.TENANT_ADMIN:
        return True
    if current_user.role in (UserRole.MENTOR, UserRole.INTERN):
        return task.assignee_id == current_user.id or task.owner_id == current_user.id
    return False


async def _validate_assignee(
    db: AsyncSession,
    assignee_id: UUID,
    tenant_id: UUID,
    current_user: User,
) -> None:
    """Validate assignee: exists, same tenant, is_active. TENANT_ADMIN: assignee must be MENTOR or INTERN; MENTOR: self or INTERN only. INTERN assignee rule enforced in create_task."""
    assignee = await user_crud.get_user(db, assignee_id)
    if not assignee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignee not found",
        )
    if assignee.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Assignee must belong to the same organization",
        )
    if not assignee.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot assign a task to an inactive account",
        )
    if current_user.role == UserRole.TENANT_ADMIN:
        if assignee.role not in (UserRole.MENTOR, UserRole.INTERN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant admins can only assign tasks to mentors or interns",
            )
    elif current_user.role == UserRole.MENTOR:
        if assignee_id != current_user.id and assignee.role != UserRole.INTERN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Mentors can only assign tasks to themselves or to interns",
            )


def _can_delete_task(current_user: User, task: Task) -> bool:
    """True if current_user can delete this task. INTERN only if owner == self."""
    if not _can_access_task(current_user, task):
        return False
    if current_user.role == UserRole.INTERN:
        return task.owner_id == current_user.id
    return current_user.role in (UserRole.TENANT_ADMIN, UserRole.MENTOR)


async def list_tasks(
    db: AsyncSession,
    current_user: User,
    tenant_id: UUID,
    skip: int = 0,
    limit: int = 10,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    assignee_id: UUID | None = None,
    owner_id: UUID | None = None,
) -> dict:
    """List tasks (role-scoped). INTERN/MENTOR: only tasks where assignee or owner == self. TENANT_ADMIN: all tenant tasks."""
    # INTERN/MENTOR use custom query filtering by assignee_id or owner_id == current_user; TENANT_ADMIN uses crud.get_tasks.
    if current_user.role in (UserRole.INTERN, UserRole.MENTOR):
        tasks = await _list_tasks_intern(
            db,
            current_user,
            tenant_id,
            skip,
            limit,
            status,
            priority,
            assignee_id,
            owner_id,
        )
        total = await _count_tasks_intern(
            db, tenant_id, current_user.id, status, priority, assignee_id, owner_id
        )
    else:
        tasks = await task_crud.get_tasks(
            db,
            tenant_id=tenant_id,
            skip=skip,
            limit=limit,
            status=status,
            priority=priority,
            assignee_id=assignee_id,
            owner_id=owner_id,
        )
        total = await task_crud.count_tasks(
            db,
            tenant_id=tenant_id,
            status=status,
            priority=priority,
            assignee_id=assignee_id,
            owner_id=owner_id,
        )

    data = [_task_to_response_ids_only(t) for t in tasks]
    return success_list_response(data, skip=skip, limit=limit, total=total)


async def _list_tasks_intern(
    db: AsyncSession,
    current_user: User,
    tenant_id: UUID,
    skip: int,
    limit: int,
    status: TaskStatus | None,
    priority: TaskPriority | None,
    assignee_id: UUID | None,
    owner_id: UUID | None,
) -> list[Task]:
    """List tasks for INTERN/MENTOR: tenant + (assignee_id == user or owner_id == user), optional status/priority/assignee_id/owner_id filters."""
    from sqlalchemy import or_, select

    from app.models import Task

    q = (
        select(Task)
        .where(
            Task.tenant_id == tenant_id,
            Task.deleted_at.is_(None),
            or_(Task.assignee_id == current_user.id, Task.owner_id == current_user.id),
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
    return list(result.scalars().all())


async def _count_tasks_intern(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    status: TaskStatus | None,
    priority: TaskPriority | None,
    assignee_id: UUID | None,
    owner_id: UUID | None,
) -> int:
    from sqlalchemy import func, or_, select

    from app.models import Task

    q = select(func.count(Task.id)).where(
        Task.tenant_id == tenant_id,
        Task.deleted_at.is_(None),
        or_(Task.assignee_id == user_id, Task.owner_id == user_id),
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


def _task_to_response(task: Task) -> dict:
    """Full task with nested tenant, owner, assignee (owner/assignee have tenant_id, no nested tenant object)."""
    def _user_without_tenant(user) -> dict | None:
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

    owner_data = _user_without_tenant(task.owner)
    assignee_data = _user_without_tenant(task.assignee)
    tenant_data = (
        TenantResponseSchema.model_validate(task.tenant).model_dump(mode="json")
        if task.tenant
        else None
    )
    return {
        "id": str(task.id),
        "tenant": tenant_data,
        "owner": owner_data,
        "assignee": assignee_data,
        "title": task.title,
        "description": task.description,
        "status": task.status.value,
        "priority": task.priority.value,
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "deleted_at": task.deleted_at.isoformat() if task.deleted_at else None,
    }


def _task_to_response_ids_only(task: Task) -> dict:
    """Task response with tenant_id, owner_id, assignee_id only (no nested objects). Used for list/create/update."""
    return {
        "id": str(task.id),
        "tenant_id": str(task.tenant_id),
        "owner_id": str(task.owner_id),
        "assignee_id": str(task.assignee_id),
        "title": task.title,
        "description": task.description,
        "status": task.status.value,
        "priority": task.priority.value,
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "deleted_at": task.deleted_at.isoformat() if task.deleted_at else None,
    }


async def get_task(db: AsyncSession, task_id: UUID, current_user: User) -> dict:
    """Get task by id (scope check)."""
    task = await task_crud.get_task(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    verify_tenant_access(current_user, task.tenant_id)
    if not _can_access_task(current_user, task):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return success_response(_task_to_response(task))


async def create_task(
    db: AsyncSession,
    data: TaskCreateSchema,
    current_user: User,
    tenant_id: UUID,
    assignee_id: UUID | None = None,
) -> dict:
    """Create task. owner_id = current_user. assignee_id from header or body (assignee_id param overrides data.assignee_id)."""
    effective_assignee_id = assignee_id
    if effective_assignee_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="assignee_id is required. Pass it in the header.",
        )
    # INTERN can only create for self (owner and assignee)
    if current_user.role == UserRole.INTERN:
        if effective_assignee_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Intern can only create tasks for self",
            )
    await _validate_assignee(db, effective_assignee_id, tenant_id, current_user)
    # Unique (owner, assignee, title) per tenant: reject duplicate.
    existing = await task_crud.get_task_by_owner_assignee_title(
        db,
        tenant_id=tenant_id,
        owner_id=current_user.id,
        assignee_id=effective_assignee_id,
        title=data.title.strip(),
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already assigned a task with this title to this assignee.",
        )
    task = await task_crud.create_task(
        db,
        tenant_id=tenant_id,
        owner_id=current_user.id,
        assignee_id=effective_assignee_id,
        title=data.title.strip(),
        description=data.description.strip() if data.description else None,
        status=TaskStatus.PENDING,
        priority=data.priority,
        deadline=data.deadline,
    )
    await db.commit()
    await db.refresh(task)
    return success_response(_task_to_response_ids_only(task))


async def update_task(
    db: AsyncSession,
    task_id: UUID,
    data: TaskUpdateSchema,
    current_user: User,
) -> dict:
    """Update task; record history for status/priority changes."""
    task = await task_crud.get_task(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    verify_tenant_access(current_user, task.tenant_id)
    if not _can_access_task(current_user, task):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )

    if data.assignee_id is not None:
        await _validate_assignee(db, data.assignee_id, task.tenant_id, current_user)
    # Enforce unique (owner, assignee, title): check with effective assignee/title and exclude current task.
    effective_assignee = (
        data.assignee_id if data.assignee_id is not None else task.assignee_id
    )
    effective_title = data.title.strip() if data.title is not None else task.title
    existing = await task_crud.get_task_by_owner_assignee_title(
        db,
        tenant_id=task.tenant_id,
        owner_id=task.owner_id,
        assignee_id=effective_assignee,
        title=effective_title,
        exclude_task_id=task.id,
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already assigned a task with this title to this assignee.",
        )

    updates = {}
    if data.title is not None:
        updates["title"] = data.title.strip()
    if data.description is not None:
        updates["description"] = data.description.strip() if data.description else None
    if data.status is not None:
        updates["status"] = data.status
    if data.priority is not None:
        updates["priority"] = data.priority
    if data.deadline is not None:
        updates["deadline"] = data.deadline
    if data.assignee_id is not None:
        updates["assignee_id"] = data.assignee_id

    old_status = task.status
    old_priority = task.priority
    for key, value in updates.items():
        setattr(task, key, value)
    await db.flush()

    # Record history only when status or priority changes (append-only audit).
    new_status = task.status
    new_priority = task.priority
    if old_status != new_status or old_priority != new_priority:
        await task_history_crud.create_history_entry(
            db,
            tenant_id=task.tenant_id,
            task_id=task.id,
            actor_id=current_user.id,
            old_status=old_status,
            new_status=new_status,
            old_priority=old_priority,
            new_priority=new_priority,
        )
    await db.commit()
    await db.refresh(task)
    return success_response(_task_to_response_ids_only(task))


async def delete_task(db: AsyncSession, task_id: UUID, current_user: User) -> None:
    """Soft-delete task. INTERN only if owner == self."""
    task = await task_crud.get_task(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    verify_tenant_access(current_user, task.tenant_id)
    if not _can_delete_task(current_user, task):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    await task_crud.soft_delete_task(db, task_id, deleted_by=current_user.id)
    await db.commit()


async def get_task_history(
    db: AsyncSession,
    task_id: UUID,
    current_user: User,
    skip: int = 0,
    limit: int = 20,
) -> dict:
    """Get task history (status/priority changes only). Scope: same as get task; 404 if task not accessible."""
    task = await task_crud.get_task(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    verify_tenant_access(current_user, task.tenant_id)
    if not _can_access_task(current_user, task):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    entries = await task_history_crud.get_history_for_task(
        db, task_id, tenant_id=task.tenant_id, skip=skip, limit=limit
    )
    data = [
        {
            "id": str(e.id),
            "task_id": str(e.task_id),
            "actor_id": str(e.actor_id),
            "old_status": e.old_status.value if e.old_status else None,
            "new_status": e.new_status.value if e.new_status else None,
            "old_priority": e.old_priority.value if e.old_priority else None,
            "new_priority": e.new_priority.value if e.new_priority else None,
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ]
    # Crud returns page only; total = len(data) for this page (no separate count query for history).
    total = len(data)
    return success_list_response(data, skip=skip, limit=limit, total=total)
