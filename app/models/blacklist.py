import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import CreatedAtMixin, UUIDMixin


class BlacklistedToken(UUIDMixin, CreatedAtMixin, Base):
    """JWT refresh token blacklist (no soft delete, no updated_at)."""

    __tablename__ = "token_blacklist"

    # FK to user; CASCADE so blacklist rows are removed when user is deleted; index for lookups by user_id.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # JWT ID (jti) from token payload; unique so the same token cannot be blacklisted twice.
    token_jti: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # Timezone-aware so we can compare with UTC; used when pruning expired entries or checking validity.
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # selectin loads user in a separate query when tokens are loaded (avoids N+1).
    user = relationship("User", back_populates="blacklisted_tokens", lazy="selectin")
