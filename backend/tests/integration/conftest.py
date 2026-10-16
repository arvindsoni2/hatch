"""Synthetic file-backed Coach fixtures shared by request and worker sessions."""

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import database
from app.config import settings
from app.database import Base, create_sqlite_engine
from app.services import coach_reconciliation


@pytest_asyncio.fixture
async def coach_database(tmp_path, monkeypatch):
    engine = create_sqlite_engine(f"sqlite+aiosqlite:///{tmp_path / 'coach.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "AsyncSessionLocal", factory)
    monkeypatch.setattr(coach_reconciliation, "AsyncSessionLocal", factory)
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", str(tmp_path / "media"))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield factory
    finally:
        await engine.dispose()
