import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import get_settings

settings = get_settings()


def get_database_url() -> str:
    """Return an async SQLAlchemy URL for PostgreSQL in production and SQLite locally."""
    if settings.DATABASE_URL:
        url = settings.DATABASE_URL.strip()

        # Neon/Supabase/Vercel may provide a standard PostgreSQL URL.
        if url.startswith("postgres://"):
            url = "postgresql+asyncpg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url[len("postgresql://"):]
        elif url.startswith("postgresql+psycopg://"):
            url = url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)

        return url

    # Local development only. Production/Vercel is rejected by config validation.
    return "sqlite+aiosqlite:///./nexora.db"


DATABASE_URL = get_database_url()

engine = create_async_engine(
    DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    # Import models before create_all so their tables are registered
    # in Base.metadata.
    from app.models import db_models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
