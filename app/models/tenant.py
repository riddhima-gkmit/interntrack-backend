from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Tenant(Base):
    """Tenant (organization) for multi-tenancy; inherits UUID, timestamps, soft delete from Base."""

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)  # Unique org name.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # False to disable tenant without deleting.

    # foreign_keys points to User.tenant_id (User has the FK); noload to avoid loading users when not needed.
    users = relationship(
        "User", foreign_keys="User.tenant_id", back_populates="tenant", lazy="noload"
    )
    invitations = relationship("Invitation", back_populates="tenant", lazy="noload")
