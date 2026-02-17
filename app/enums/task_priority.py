"""Task priority: low, medium, high. Used in task model, API, and task history."""

from enum import StrEnum

class TaskPriority(StrEnum):
    """Priority level of a task."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
