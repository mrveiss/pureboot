"""Database connection and session management."""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import settings

engine = create_async_engine(
    settings.database.url,
    echo=settings.database.echo,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Alias for scheduler use
async_session_factory = async_session


def get_database_url() -> str:
    """Get the database URL for async connections."""
    return settings.database.url


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database sessions."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Initialize database tables and run migrations."""
    from src.db.models import Base
    from src.db.migrations import run_migrations

    async with engine.begin() as conn:
        # Create any new tables
        await conn.run_sync(Base.metadata.create_all)

        # Run migrations for existing tables (add missing columns)
        await run_migrations(conn)


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()
