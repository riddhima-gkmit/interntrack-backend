"""Refresh token blacklist: check by JTI (JWT ID from payload) and add on logout/refresh. Auth service uses this to reject revoked or already-used refresh tokens."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BlacklistedToken


async def is_token_blacklisted(db: AsyncSession, jti: str) -> bool:
    """Return True if the JTI is in the blacklist. Called on refresh (reject if blacklisted) and logout (avoid double-add)."""
    result = await db.execute(
        select(BlacklistedToken).where(BlacklistedToken.token_jti == jti)
    )
    return result.scalar_one_or_none() is not None


async def blacklist_token(
    db: AsyncSession, user_id: UUID, jti: str, expires_at: datetime
) -> BlacklistedToken:
    """Add a token JTI to the blacklist. expires_at from token payload (for pruning expired rows later). Caller must commit."""
    row = BlacklistedToken(
        user_id=user_id,
        token_jti=jti,
        expires_at=expires_at,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row
