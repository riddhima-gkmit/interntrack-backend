"""Async SQLAlchemy engine and session factory. Converts sync PostgreSQL URL to async driver."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# Same .env can use postgresql:// or postgresql+psycopg2:// (e.g. Alembic); we need asyncpg for the app.
_url = settings.DATABASE_URL
if _url.startswith("postgresql+psycopg2://"):
    _url = "postgresql+asyncpg://" + _url[len("postgresql+psycopg2://") :]
elif _url.startswith("postgresql://"):
    _url = "postgresql+asyncpg://" + _url[len("postgresql://") :]

engine = create_async_engine(
    _url,
    echo=settings.DEBUG,  # Log SQL when DEBUG is True.
    pool_pre_ping=True,  # Check connection is alive before use (handles stale DB connections).
    pool_size=5,
    max_overflow=10,  # Allow up to 15 total connections (5 + 10) under load.
    pool_recycle=3600,  # Recycle connections after 1 hour (avoids DB timeout / stale connections).
    pool_timeout=30,  # Seconds to wait for a connection from the pool before giving up.
)

# Session factory: use async with async_session() as session in get_db().
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Objects remain usable after commit (no lazy load after commit).
    autoflush=False,  # Don't flush before every query; explicit flush/commit in services.
)
