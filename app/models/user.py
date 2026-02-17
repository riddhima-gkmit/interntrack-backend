import uuid

from sqlalchemy import Boolean
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import UserRole
from app.models.base import Base


class User(Base):
    """User account; tenant_id is null for SUPER_ADMIN (global admin, not tied to a tenant)."""

    __tablename__ = "users"
    # Unique username and email globally (across all tenants).
    __table_args__ = (
        UniqueConstraint("username", name="uq_user_username"),
        UniqueConstraint("email", name="uq_user_email"),
    )

    # Nullable for SUPER_ADMIN; CASCADE when tenant is deleted; index for tenant-scoped queries.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    username: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)  # Index for login/lookups.
    first_name: Mapped[str] = mapped_column(String(150), nullable=False)
    last_name: Mapped[str] = mapped_column(String(150), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)  # Bcrypt hash; never store plaintext.
    # native_enum=False for DB portability; default INTERN.
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, native_enum=False),
        default=UserRole.INTERN,
        nullable=False,
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # True after email verification.
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # False until activated (e.g. by admin or post-verify).

    # joined: load tenant in same query when loading user (common for auth/context).
    tenant = relationship(
        "Tenant", foreign_keys=[tenant_id], back_populates="users", lazy="joined"
    )
    blacklisted_tokens = relationship(
        "BlacklistedToken", back_populates="user", lazy="noload"
    )
    # foreign_keys disambiguates when Comment has multiple FKs to User (if any).
    comments = relationship(
        "Comment", foreign_keys="Comment.user_id", back_populates="user", lazy="noload"
    )
    invitations_created = relationship(
        "Invitation",
        foreign_keys="Invitation.created_by_id",
        back_populates="created_by",
        lazy="noload",
    )
