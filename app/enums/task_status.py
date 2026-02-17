"""Task status: pending, in_progress, completed. Used in task model, API, and task history."""

from enum import StrEnum

class TaskStatus(StrEnum):
    """Lifecycle status of a task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
