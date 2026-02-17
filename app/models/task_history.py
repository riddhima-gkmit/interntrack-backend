import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base as DeclarativeBase
from app.enums import TaskPriority, TaskStatus
from app.models.mixins import CreatedAtMixin, UUIDMixin


class TaskHistory(UUIDMixin, CreatedAtMixin, DeclarativeBase):
    """Append-only log of task status/priority changes (CreatedAtMixin, no updated_at)."""

    __tablename__ = "task_history"

    # FK to tenant; CASCADE when tenant deleted; index for tenant-scoped queries.
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # FK to task; CASCADE when task deleted; index for listing history by task.
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # FK to user who made the change; CASCADE when user deleted.
    actor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nullable: only status or only priority may change in one update; null = unchanged/not applicable.
    old_status: Mapped[TaskStatus | None] = mapped_column(
        SAEnum(TaskStatus, native_enum=False),
        nullable=True,
    )
    new_status: Mapped[TaskStatus | None] = mapped_column(
        SAEnum(TaskStatus, native_enum=False),
        nullable=True,
    )
    old_priority: Mapped[TaskPriority | None] = mapped_column(
        SAEnum(TaskPriority, native_enum=False),
        nullable=True,
    )
    new_priority: Mapped[TaskPriority | None] = mapped_column(
        SAEnum(TaskPriority, native_enum=False),
        nullable=True,
    )

    # noload: load task/actor explicitly when needed (e.g. for audit display).
    task = relationship("Task", back_populates="history", lazy="noload")
    actor = relationship("User", lazy="noload")
