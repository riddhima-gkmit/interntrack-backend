"""SQLAlchemy declarative base; concrete models inherit from app.models.base.Base (which adds UUID, timestamps, soft delete)."""

from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """Declarative base for all models; used by engine/session in app.database.session."""
    pass
