"""Tests for JobClassifier — batch classification and LLM response formats."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.job_classifier import JobClassifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_job(title: str = "Cloud Architect", description: str = "Contract AWS role") -> MagicMock:
    job = MagicMock()
    job.id = str(uuid.uuid4())
    job.title = title
    job.description = description
    job.rate_text = "£700/day"
    job.location = "London"
    job.match_score = None
    job.is_active = True
    return job


SAMPLE_CLASSIFICATION = {
    "employment_type": "contract",
    "ir35_status": "outside",
    "working_pattern": "hybrid",
    "seniority": "senior",
    "match_score": 82,
    "match_reasons": ["AWS expertise matches", "Outside IR35"],
    "red_flags": [],
}


def make_mock_model(response_text: str) -> MagicMock:
    model = MagicMock()
    msg = MagicMock()
    msg.content = response_text
    model.ainvoke = AsyncMock(return_value=msg)
    return model


# ---------------------------------------------------------------------------
# classify_batch — response format variants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classify_batch_handles_dict_response():
    """LLM returns {"jobs": [...]} — standard dict format is parsed correctly."""
    job = make_job()
    response = json.dumps({"jobs": [{**SAMPLE_CLASSIFICATION, "id": job.id}]})

    with patch("app.services.job_classifier.get_triage_model", return_value=make_mock_model(response)):
        classifier = JobClassifier()
        results = await classifier.classify_batch([job])

    assert len(results) == 1
    assert results[0]["id"] == job.id
    assert results[0]["employment_type"] == "contract"


@pytest.mark.asyncio
async def test_classify_batch_handles_bare_list_response():
    """LLM returns a bare list [...] instead of {"jobs": [...]} — must not raise AttributeError.

    This is the exact format phi3:mini returns; the isinstance guard added in
    commit 01e5999 protects against the silent crash this caused in production.
    """
    job = make_job()
    response = json.dumps([{**SAMPLE_CLASSIFICATION, "id": job.id}])

    with patch("app.services.job_classifier.get_triage_model", return_value=make_mock_model(response)):
        classifier = JobClassifier()
        results = await classifier.classify_batch([job])

    assert len(results) == 1
    assert results[0]["id"] == job.id
    assert results[0]["ir35_status"] == "outside"


@pytest.mark.asyncio
async def test_classify_batch_handles_markdown_fenced_json():
    """LLM wraps JSON in a ```json … ``` fence — stripped correctly."""
    job = make_job()
    inner = json.dumps([{**SAMPLE_CLASSIFICATION, "id": job.id}])
    response = f"```json\n{inner}\n```"

    with patch("app.services.job_classifier.get_triage_model", return_value=make_mock_model(response)):
        classifier = JobClassifier()
        results = await classifier.classify_batch([job])

    assert len(results) == 1


@pytest.mark.asyncio
async def test_classify_batch_returns_empty_list_on_invalid_json():
    """Malformed JSON from LLM logs an error and returns [] without crashing."""
    job = make_job()

    with patch("app.services.job_classifier.get_triage_model", return_value=make_mock_model("not valid json")):
        classifier = JobClassifier()
        results = await classifier.classify_batch([job])

    assert results == []


@pytest.mark.asyncio
async def test_classify_batch_returns_empty_list_for_empty_input():
    """Empty jobs list short-circuits immediately without calling the LLM."""
    with patch("app.services.job_classifier.get_triage_model") as mock_factory:
        classifier = JobClassifier()
        results = await classifier.classify_batch([])

    assert results == []
    mock_factory.assert_not_called()


@pytest.mark.asyncio
async def test_classify_batch_handles_llm_exception():
    """LLM raising an exception returns [] without propagating the error."""
    job = make_job()
    broken_model = MagicMock()
    broken_model.ainvoke = AsyncMock(side_effect=RuntimeError("Ollama died"))

    with patch("app.services.job_classifier.get_triage_model", return_value=broken_model):
        classifier = JobClassifier()
        results = await classifier.classify_batch([job])

    assert results == []


# ---------------------------------------------------------------------------
# run_pending — DB integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_pending_returns_zero_when_no_jobs(db_session):
    """run_pending on an empty DB returns 0 without error."""
    with patch("app.services.job_classifier.get_triage_model", return_value=make_mock_model("[]")):
        classifier = JobClassifier()
        count = await classifier.run_pending(db_session)

    assert count == 0


@pytest.mark.asyncio
async def test_run_pending_classifies_jobs_in_db(db_session):
    """run_pending fetches unclassified jobs, calls LLM, and writes match_score to DB."""
    from app.models.job import JobPosting

    job_id = str(uuid.uuid4())
    job = JobPosting(
        id=job_id,
        title="AWS Architect",
        company="Test Co",
        location="London",
        rate_text="£700/day",
        rate_min=700.0,
        rate_max=700.0,
        currency="GBP",
        ir35_status="outside",
        description="Contract AWS architect role.",
        url=f"https://example.com/jobs/{job_id}",
        source="contractoruk",
        scraped_at=datetime.utcnow(),
        is_active=True,
        match_score=None,
    )
    db_session.add(job)
    await db_session.commit()

    classification_response = json.dumps([{**SAMPLE_CLASSIFICATION, "id": job_id}])

    with patch("app.services.job_classifier.get_triage_model", return_value=make_mock_model(classification_response)):
        classifier = JobClassifier()
        count = await classifier.run_pending(db_session)

    assert count == 1

    await db_session.refresh(job)
    assert job.match_score == pytest.approx(0.82)
    assert job.ir35_status == "outside"
    assert job.employment_type == "contract"


@pytest.mark.asyncio
async def test_run_pending_caps_batches_for_bundled_triage_context(db_session):
    """Large configured batches are split to fit the bundled 2048-token slot."""
    from app.models.job import JobPosting

    jobs = []
    for index in range(8):
        job = JobPosting(
            id=str(uuid.uuid4()),
            title=f"Cloud Architect {index}",
            company="Test Co",
            location="London",
            description="Cloud architecture role. " * 20,
            url=f"https://example.com/context-safe-{index}",
            source="test",
            scraped_at=datetime.utcnow(),
            is_active=True,
            match_score=None,
        )
        jobs.append(job)
        db_session.add(job)
    await db_session.commit()

    classifier = JobClassifier()
    seen_batch_sizes: list[int] = []

    async def classify(batch):
        seen_batch_sizes.append(len(batch))
        return [
            {**SAMPLE_CLASSIFICATION, "id": job.id}
            for job in batch
        ]

    classifier.classify_batch = AsyncMock(side_effect=classify)
    with patch("app.services.job_classifier.settings.CLASSIFIER_BATCH_SIZE", 30):
        count = await classifier.run_pending(db_session)

    assert count == 8
    assert seen_batch_sizes == [3, 3, 2]
