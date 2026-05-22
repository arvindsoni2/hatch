"""Shared pytest fixtures for JobPilot backend tests."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.job import JobPosting
from app.schemas.job import JobPostingCreate

# ──────────────────────── In-Memory SQLite Test DB ────────────────────────

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

TestAsyncSession = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a fresh in-memory SQLite session per test, with tables created."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestAsyncSession() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTPX test client with the in-memory DB injected."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ──────────────────────── Sample Data Factories ────────────────────────

def make_job_create(
    title: str | None = None,
    company: str = "Test Corp",
    location: str = "London, UK",
    source: str = "contractoruk",
    ir35_status: str = "outside",
    rate_min: float = 600.0,
    rate_max: float = 700.0,
    url: str | None = None,
    description: str = "A senior solutions architect role for cloud migration.",
) -> JobPostingCreate:
    """Create a sample JobPostingCreate for testing.

    Args:
        title: Job title.
        company: Company name.
        location: Location string.
        source: Scraper source name.
        ir35_status: IR35 status ('inside', 'outside', 'unknown').
        rate_min: Minimum daily rate.
        rate_max: Maximum daily rate.
        url: Optional URL override (defaults to unique UUID URL).

    Returns:
        JobPostingCreate instance ready for use in tests.
    """
    if url is None:
        url = f"https://example.com/jobs/{uuid.uuid4()}"
    if title is None:
        title = f"Solutions Architect {uuid.uuid4().hex[:6]}"
    return JobPostingCreate(
        title=title,
        company=company,
        location=location,
        rate_text=f"£{rate_min:.0f}-£{rate_max:.0f}/day",
        rate_min=rate_min,
        rate_max=rate_max,
        currency="GBP",
        ir35_status=ir35_status,
        contract_length="6 months",
        description=description,
        url=url,
        source=source,
        posted_at=datetime.utcnow(),
        skills=["AWS", "Terraform", "Kubernetes"],
    )


@pytest_asyncio.fixture
async def sample_job(db_session: AsyncSession) -> JobPosting:
    """Insert and return a single sample JobPosting in the test database."""
    job = JobPosting(
        id=str(uuid.uuid4()),
        title="Cloud Architect — AWS",
        company="Sample Corp",
        location="London, UK",
        rate_text="£700/day",
        rate_min=700.0,
        rate_max=700.0,
        currency="GBP",
        ir35_status="outside",
        contract_length="6 months",
        description="Contract cloud architect role. Outside IR35.",
        url=f"https://example.com/jobs/{uuid.uuid4()}",
        source="reed",
        scraped_at=datetime.utcnow(),
        skills=["AWS", "Terraform"],
        is_active=True,
        sync_status="pending",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


# ──────────────────────── Phase 2 factories ────────────────────────

from app.schemas.application import ApplicationCreate  # noqa: E402


def make_application_create(
    job_id: str | None = None,
    status: str = "discovered",
    priority: str = "normal",
    notes: str | None = None,
    agency_name: str | None = "Test Agency",
) -> ApplicationCreate:
    """Create a sample ApplicationCreate for testing.

    Args:
        job_id: Optional linked job posting UUID.
        status: Initial application status.
        priority: Application priority level.
        notes: Optional notes text.
        agency_name: Optional agency name.

    Returns:
        ApplicationCreate instance ready for use in tests.
    """
    return ApplicationCreate(
        job_id=job_id,
        status=status,
        priority=priority,
        notes=notes,
        agency_name=agency_name,
    )


@pytest_asyncio.fixture
async def sample_application(db_session: AsyncSession):
    """Insert and return a single sample Application in the test database."""
    from app.models.application import Application

    app = Application(
        id=str(uuid.uuid4()),
        job_id=None,
        status="discovered",
        priority="normal",
        agency_name="Sample Agency",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)
    return app
