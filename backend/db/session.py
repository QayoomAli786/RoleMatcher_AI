"""Async database session management with SQLAlchemy.

Uses asyncpg with Supabase pgbouncer compatibility:
- prepared_statement_cache_size=0 disables prepared statements
- NullPool for SQLite, default pool for PostgreSQL
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


_url = settings.postgres_url
_is_sqlite = _url.startswith("sqlite")

if _is_sqlite:
    engine = create_async_engine(
        _url,
        echo=settings.debug,
        pool_pre_ping=False,
        poolclass=NullPool,
    )
else:
    engine = create_async_engine(
        _url,
        echo=settings.debug,
        pool_pre_ping=True,
        connect_args={"prepared_statement_cache_size": 0},
    )

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Create all tables (for development; use Alembic in production).

    Gracefully skips if PostgreSQL is unreachable so the app can still
    serve non-DB endpoints (health, docs, etc.).
    """
    try:
        async with engine.begin() as conn:
            from backend.core.models import Base

            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created / verified")
    except Exception as exc:
        logger.warning(
            "Could not connect to PostgreSQL (%s). "
            "DB-dependent endpoints will fail until the database is available.",
            exc,
        )


async def close_db() -> None:
    """Dispose of the connection pool on shutdown."""
    try:
        await engine.dispose()
    except Exception:
        pass
