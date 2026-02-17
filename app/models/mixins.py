import uuid
from datetime import UTC, datetime

from sqlalchemy import UUID, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, declared_attr, mapped_column
from sqlalchemy.sql import func


class UUIDMixin:
    """Mixin adding a UUID primary key."""

    # Application-generated UUID (default=uuid.uuid4); UUID(as_uuid=True) gives Python uuid type.
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Mixin adding created_at and updated_at timestamps (server-side so DB is source of truth)."""

    # server_default so DB sets value on INSERT (timezone-aware).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # onupdate=func.now() so DB updates this on every UPDATE.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CreatedAtMixin:
    """Mixin adding only created_at (for append-only / audit tables)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """
    Mixin for soft delete using deleted_at and deleted_by (per InternTrack ER).
    Filter active records with deleted_at.is_(None).
    """

    # Null = active; set to timestamp when soft-deleted (timezone-aware).
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # FK to user who deleted; SET NULL if that user is deleted (keep audit trail best-effort).
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    def soft_delete(self, deleted_by_id: uuid.UUID | None = None) -> None:
        """Mark as deleted. Optionally set deleted_by for audit."""
        self.deleted_at = datetime.now(UTC)
        if deleted_by_id is not None:
            self.deleted_by = deleted_by_id

    def restore(self) -> None:
        """Clear soft delete."""
        self.deleted_at = None
        self.deleted_by = None


class TenantMixin:
    """Mixin adding tenant_id FK for multi-tenant tables."""

    # declared_attr so each subclass gets its own column descriptor (required for mixins).
    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
