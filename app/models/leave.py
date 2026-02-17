import uuid
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import LeaveStatus, LeaveType
from app.models.base import Base
from app.models.mixins import TenantMixin


class Leave(TenantMixin, Base):
    """Leave request; scoped by tenant. user_id = requester, approved_by set on approve/reject."""

    __tablename__ = "leaves"

    # FK to requester; CASCADE when user is deleted; index for listing leaves by user.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # native_enum=False stores string in DB for portability.
    leave_type: Mapped[LeaveType] = mapped_column(
        SAEnum(LeaveType, native_enum=False),
        nullable=False,
    )
    start_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Default PENDING; set to APPROVED/REJECTED when reviewed; native_enum=False for DB portability.
    status: Mapped[LeaveStatus] = mapped_column(
        SAEnum(LeaveStatus, native_enum=False),
        default=LeaveStatus.PENDING,
        nullable=False,
    )
    # FK to user who approved/rejected; SET NULL so leave record is kept if approver is deleted.
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)  # Optional reason/notes.

    # foreign_keys needed when mixin has multiple FKs; noload to avoid loading when not needed.
    tenant = relationship("Tenant", foreign_keys="Leave.tenant_id", lazy="noload")
    user = relationship("User", foreign_keys=[user_id], lazy="noload")
    approver = relationship("User", foreign_keys=[approved_by], lazy="noload")
