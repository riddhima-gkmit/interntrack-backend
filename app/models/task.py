import uuid
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import TaskPriority, TaskStatus
from app.models.base import Base
from app.models.mixins import TenantMixin


class Task(TenantMixin, Base):
    """Task; scoped by tenant. owner_id/assignee_id reference users."""

    __tablename__ = "tasks"

    # FK to task creator; CASCADE when user deleted; index for listing by owner.
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # FK to assigned user; CASCADE when user deleted; index for listing by assignee.
    assignee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)  # Text for longer content.
    # native_enum=False for DB portability; default PENDING.
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, native_enum=False),
        default=TaskStatus.PENDING,
        nullable=False,
    )
    # native_enum=False for DB portability; default MEDIUM.
    priority: Mapped[TaskPriority] = mapped_column(
        SAEnum(TaskPriority, native_enum=False),
        default=TaskPriority.MEDIUM,
        nullable=False,
    )
    deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # Optional; timezone-aware for consistent comparison.

    # foreign_keys required (two FKs to User); joined loads owner/assignee/tenant in same query when loading task.
    owner = relationship("User", foreign_keys=[owner_id], lazy="joined")
    assignee = relationship("User", foreign_keys=[assignee_id], lazy="joined")
    tenant = relationship("Tenant", foreign_keys="Task.tenant_id", lazy="joined")
    # noload: load comments/history explicitly when needed (e.g. detail view).
    comments = relationship("Comment", back_populates="task", lazy="noload")
    history = relationship("TaskHistory", back_populates="task", lazy="noload")
