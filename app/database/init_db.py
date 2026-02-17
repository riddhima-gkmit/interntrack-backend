"""Dependency that yields a DB session per request; session is closed after the request."""

import logging

from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import async_session

logger = logging.getLogger(__name__)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session for the request lifecycle; use as Depends(get_db) in route handlers and dependencies."""
    # Each request gets its own session; async with ensures it is closed when the request ends (after yield).
    async with async_session() as session:
        yield session
