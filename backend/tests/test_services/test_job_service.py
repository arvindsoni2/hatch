"""Unit tests for JobService — save_jobs, dedup logic, and scraper dispatch."""
from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.job_repository import JobRepository
from app.schemas.job import JobPostingCreate, JobPostingRead, ScrapeResult
from app.services.dedup import DedupService
from app.services.job_service import JobService
from tests.conftest import make_job_create


# ──────────────────────── Fixtures ────────────────────────

@pytest_asyncio.fixture
async def job_service(db_session: AsyncSession) -> JobService:
    """Create a real JobService backed by the in-memory test DB."""
    repo = JobRepository(db_session)
    return JobService(repo)


# ──────────────────────── save_jobs ────────────────────────

class TestSaveJobs:
    @pytest.mark.asyncio
    async def test_saves_new_jobs(self, job_service: JobService) -> None:
        jobs = [make_job_create() for _ in range(3)]
        result = await job_service.save_jobs(jobs, source="test")
        assert result.jobs_found == 3
        assert result.jobs_new == 3
        assert result.errors == 0
        assert result.source == "test"

    @pytest.mark.asyncio
    async def test_skips_url_duplicates(self, job_service: JobService) -> None:
        shared_url = f"https://example.com/jobs/{uuid.uuid4()}"
        job1 = make_job_create(url=shared_url)
        job2 = make_job_create(url=shared_url, title="Slightly Different Title")

        result1 = await job_service.save_jobs([job1], source="test")
        assert result1.jobs_new == 1

        result2 = await job_service.save_jobs([job2], source="test")
        assert result2.jobs_new == 0  # Duplicate URL — skipped

    @pytest.mark.asyncio
    async def test_returns_scrape_result(self, job_service: JobService) -> None:
        jobs = [make_job_create()]
        result = await job_service.save_jobs(jobs, source="reed")
        assert isinstance(result, ScrapeResult)
        assert result.source == "reed"
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_empty_job_list(self, job_service: JobService) -> None:
        result = await job_service.save_jobs([], source="test")
        assert result.jobs_found == 0
        assert result.jobs_new == 0
        assert result.errors == 0

    @pytest.mark.asyncio
    async def test_handles_save_error_gracefully(self, job_service: JobService) -> None:
        """Test that one bad job doesn't abort the whole batch."""
        good_job = make_job_create()
        bad_job = make_job_create()

        # Monkey-patch repo.create to raise on the bad job
        original_create = job_service._repo.create
        call_count = 0

        async def flaky_create(job: JobPostingCreate) -> JobPostingRead:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("Simulated DB error")
            return await original_create(job)

        job_service._repo.create = flaky_create  # type: ignore[method-assign]

        result = await job_service.save_jobs([good_job, bad_job], source="test")
        assert result.jobs_found == 2
        assert result.jobs_new == 1
        assert result.errors == 1


# ──────────────────────── run_scraper ────────────────────────

class TestRunScraper:
    @pytest.mark.asyncio
    async def test_raises_for_unknown_source(self, job_service: JobService) -> None:
        with pytest.raises(ValueError, match="Unknown scraper source"):
            await job_service.run_scraper("nonexistent_board")

    @pytest.mark.asyncio
    async def test_runs_known_source_with_mocked_scraper(self, job_service: JobService) -> None:
        mock_jobs = [make_job_create(source="reed") for _ in range(5)]

        with patch("app.services.job_service._load_scraper_class") as mock_load:
            mock_scraper_cls = MagicMock()
            mock_instance = MagicMock()
            mock_instance.scrape = AsyncMock(return_value=mock_jobs)
            mock_scraper_cls.return_value = mock_instance
            mock_load.return_value = mock_scraper_cls

            result = await job_service.run_scraper("reed")

        assert result.source == "reed"
        assert result.jobs_found == 5
        assert result.jobs_new == 5

    @pytest.mark.asyncio
    async def test_handles_scraper_exception(self, job_service: JobService) -> None:
        with patch("app.services.job_service._load_scraper_class") as mock_load:
            mock_scraper_cls = MagicMock()
            mock_instance = MagicMock()
            mock_instance.scrape = AsyncMock(side_effect=Exception("Network error"))
            mock_scraper_cls.return_value = mock_instance
            mock_load.return_value = mock_scraper_cls

            result = await job_service.run_scraper("reed")

        assert result.errors >= 1
        assert result.jobs_new == 0


# ──────────────────────── DedupService ────────────────────────

class TestDedupService:
    @pytest.mark.asyncio
    async def test_no_duplicate_for_empty_db(self, db_session: AsyncSession) -> None:
        repo = JobRepository(db_session)
        dedup = DedupService()
        result = await dedup.is_duplicate("Senior Solutions Architect", "TestCo", repo)
        assert result is False

    @pytest.mark.asyncio
    async def test_detects_near_duplicate(self, db_session: AsyncSession, sample_job: object) -> None:
        repo = JobRepository(db_session)
        dedup = DedupService()

        # "Cloud Architect — AWS" vs "Cloud Architect AWS" — very similar
        result = await dedup.is_duplicate(
            "Cloud Architect AWS",
            "Sample Corp",
            repo,
        )
        assert result is True  # Should be detected as duplicate

    @pytest.mark.asyncio
    async def test_no_false_positive_for_different_jobs(
        self, db_session: AsyncSession, sample_job: object
    ) -> None:
        repo = JobRepository(db_session)
        dedup = DedupService()

        result = await dedup.is_duplicate(
            "DevOps Engineer",
            "Completely Different Company",
            repo,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_find_similar_returns_matches(
        self, db_session: AsyncSession, sample_job: object
    ) -> None:
        repo = JobRepository(db_session)
        dedup = DedupService()

        similar = await dedup.find_similar("Cloud Architect", repo, threshold=70.0)
        assert len(similar) >= 1
        assert any("Cloud Architect" in j.title for j in similar)


# ──────────────────────── Repository Integration ────────────────────────

class TestJobRepository:
    @pytest.mark.asyncio
    async def test_create_and_get_by_url(self, db_session: AsyncSession) -> None:
        repo = JobRepository(db_session)
        job = make_job_create()
        created = await repo.create(job)
        fetched = await repo.get_by_url(job.url)
        assert fetched is not None
        assert fetched.id == created.id

    @pytest.mark.asyncio
    async def test_get_by_id(self, db_session: AsyncSession) -> None:
        repo = JobRepository(db_session)
        job = make_job_create()
        created = await repo.create(job)
        fetched = await repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.title == job.title

    @pytest.mark.asyncio
    async def test_soft_delete(self, db_session: AsyncSession) -> None:
        repo = JobRepository(db_session)
        job = make_job_create()
        created = await repo.create(job)
        deleted = await repo.soft_delete(created.id)
        assert deleted is True
        fetched = await repo.get_by_id(created.id)
        assert fetched is None  # Soft-deleted — not returned

    @pytest.mark.asyncio
    async def test_list_with_filters_ir35(self, db_session: AsyncSession) -> None:
        repo = JobRepository(db_session)
        await repo.create(make_job_create(ir35_status="outside"))
        await repo.create(make_job_create(ir35_status="inside"))
        await repo.create(make_job_create(ir35_status="outside"))

        outside_jobs, total = await repo.list_with_filters(ir35_status="outside")
        assert total == 2
        assert all(j.ir35_status == "outside" for j in outside_jobs)

    @pytest.mark.asyncio
    async def test_list_with_search(self, db_session: AsyncSession) -> None:
        repo = JobRepository(db_session)
        await repo.create(make_job_create(title="Senior Solutions Architect AWS", description="Cloud migration role outside IR35."))
        await repo.create(make_job_create(title="DevOps Engineer Kubernetes", description="DevOps pipeline role with Kubernetes."))

        results, total = await repo.list_with_filters(search="Solutions Architect")
        assert total == 1
        assert "Solutions Architect" in results[0].title

    @pytest.mark.asyncio
    async def test_get_stats(self, db_session: AsyncSession) -> None:
        repo = JobRepository(db_session)
        for source in ["reed", "reed", "adzuna"]:
            await repo.create(make_job_create(source=source))

        stats = await repo.get_stats()
        assert stats.total_jobs == 3
        assert stats.by_source.get("reed") == 2
        assert stats.by_source.get("adzuna") == 1
        assert stats.new_today == 3  # All scraped just now
