"""SQLAlchemy async database engine, session, and helpers."""
from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from .config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# Ensure the data directory exists (SQLite file path)
_db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")
_db_dir = os.path.dirname(_db_path)
if _db_dir and not os.path.exists(_db_dir):
    os.makedirs(_db_dir, exist_ok=True)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.LOG_LEVEL == "DEBUG",
    poolclass=NullPool,
    connect_args={
        "check_same_thread": False,
        "timeout": 30,
    },
)


@event.listens_for(engine.sync_engine, "connect")
def _set_wal_mode(dbapi_connection: object, _connection_record: object) -> None:
    """Enable WAL journal mode for better concurrent write performance."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Create all tables defined in ORM models. Called on app startup."""
    # Import models to ensure they are registered with Base
    from .models import job as _job_models  # noqa: F401
    from .models import application as _app_models  # noqa: F401
    from .models import activity as _act_models  # noqa: F401
    from .models import document as _doc_models  # noqa: F401
    from .models import coach_session as _coach_models  # noqa: F401
    from .models import recruiter as _recruiter_models  # noqa: F401
    from .models import follow_up_email as _email_models  # noqa: F401
    from .models import agency_reputation as _agency_models  # noqa: F401
    from .models import async_job as _async_job_models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialised — all tables created/verified.")
