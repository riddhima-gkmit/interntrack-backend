from app.database import Base as DeclarativeBase
from app.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDMixin


class Base(UUIDMixin, TimestampMixin, SoftDeleteMixin, DeclarativeBase):
    """Base model for InternTrack: UUID, timestamps, soft delete (deleted_at, deleted_by)."""

    __abstract__ = True
