import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import get_settings

settings = get_settings()


def get_database_url() -> str:
    if settings.DATABASE_URL:
        url = settings.DATABASE_URL.strip()
        if url.startswith("postgres://"):
            return "postgresql+asyncpg://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            return "postgresql+asyncpg://" + url[len("postgresql://"):]
        if url.startswith("postgresql+psycopg://"):
            return url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
        return url

    # Vercel's filesystem is ephemeral/read-only outside /tmp. This fallback
    # keeps the function importable and lets health/status endpoints work when
    # no production database has been configured. Auth/data persistence still
    # requires DATABASE_URL to be supplied by the deployment environment.
    if os.getenv("VERCEL") == "1":
        return "sqlite+aiosqlite:////tmp/nexora.db"
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
    from app.models import db_models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
