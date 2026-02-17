"""Task schemas: create and update (partial). Owner and tenant come from JWT/route; assignee_id from header or body in create."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.enums import TaskPriority, TaskStatus


def _normalize_priority(v: TaskPriority | str) -> TaskPriority | str:
    """Lowercase string so enum accepts any casing (e.g. HIGH, high)."""
    if isinstance(v, str):
        return v.strip().lower()
    return v


def _normalize_status(v: TaskStatus | str) -> TaskStatus | str:
    """Lowercase string so enum accepts any casing."""
    if isinstance(v, str):
        return v.strip().lower()
    return v


def _deadline_not_in_past(v: datetime | None) -> datetime | None:
    """Raise if deadline is in the past. Naive datetime is treated as UTC for comparison."""
    if v is None:
        return None
    now = datetime.now(UTC)
    if v.tzinfo is None:
        v = v.replace(tzinfo=UTC)
    if v < now:
        raise ValueError("Deadline must not be in the past")
    return v


class TaskCreateSchema(BaseModel):
    """Create task. Router passes assignee_id from header (or body); owner and tenant from current_user/JWT."""

    title: str
    description: str | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    deadline: datetime | None = None  # Optional; validated not in past.

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, v: TaskPriority | str) -> TaskPriority | str:
        return _normalize_priority(v)

    @field_validator("deadline")
    @classmethod
    def deadline_not_in_past(cls, v: datetime | None) -> datetime | None:
        return _deadline_not_in_past(v)


class TaskUpdateSchema(BaseModel):
    """Update task (PATCH): all fields optional. Only provided fields are applied. Status/priority changes are logged in task history."""

    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    deadline: datetime | None = None  # Validated not in past if provided.
    assignee_id: UUID | None = None  # Reassign task; service enforces role (e.g. INTERN only self).

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: TaskStatus | str | None) -> TaskStatus | str | None:
        if v is None:
            return v
        return _normalize_status(v)

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(
        cls, v: TaskPriority | str | None
    ) -> TaskPriority | str | None:
        if v is None:
            return v
        return _normalize_priority(v)

    @field_validator("deadline")
    @classmethod
    def deadline_not_in_past(cls, v: datetime | None) -> datetime | None:
        return _deadline_not_in_past(v)
