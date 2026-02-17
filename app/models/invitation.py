import uuid
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import InvitationRole
from app.models.base import Base


class Invitation(Base):
    """Invitation to join a tenant with a given role. MENTOR creates for INTERN (or MENTOR)."""

    __tablename__ = "invitations"

    # FK to tenant; CASCADE when tenant is deleted; index for listing by tenant.
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # FK to user who sent the invite; CASCADE when user is deleted.
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)  # Invitee email; index for lookups.
    # native_enum=False stores string in DB for portability across databases.
    role: Mapped[InvitationRole] = mapped_column(
        SAEnum(InvitationRole, native_enum=False),
        nullable=False,
    )
    # Single-use token for accept link; unique so each invite has one token; index for token lookup.
    token: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Set when invitee accepts; null until then (used to filter pending vs accepted).
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    tenant = relationship("Tenant", back_populates="invitations", lazy="noload")
    # foreign_keys disambiguates when User has multiple FKs to this table.
    created_by = relationship("User", foreign_keys=[created_by_id], back_populates="invitations_created", lazy="noload")
