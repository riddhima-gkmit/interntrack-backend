import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TenantMixin


class Comment(TenantMixin, Base):
    """Comment on a task; scoped by tenant (TenantMixin adds tenant_id)."""

    __tablename__ = "comments"

    # FK to task; CASCADE so comments are removed when task is deleted; index for listing by task_id.
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # FK to comment author; CASCADE when user is deleted; index for lookups by user.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)  # Text for longer content.

    # noload: don't load task when loading comment (load explicitly when needed).
    task = relationship("Task", back_populates="comments", lazy="noload")
    # foreign_keys needed if mixin has multiple FKs; joined loads tenant in same query.
    tenant = relationship("Tenant", foreign_keys="Comment.tenant_id", lazy="joined")
    # foreign_keys disambiguates when User has multiple FKs; noload same as task.
    user = relationship("User", foreign_keys=[user_id], back_populates="comments",lazy="noload")
