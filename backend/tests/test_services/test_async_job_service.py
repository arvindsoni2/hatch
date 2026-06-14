"""Tests for AsyncJobService."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

import asyncio

from app.services.async_job_service import AsyncJobService, _error_message


@pytest.mark.asyncio
async def test_create_returns_pending_job(db_session):
    """AsyncJobService.create persists a pending job and returns it."""
    job = await AsyncJobService.create(db_session, "tailor_analyse")

    assert job.id is not None
    assert job.type == "tailor_analyse"
    assert job.status == "pending"


@pytest.mark.asyncio
async def test_finish_sets_done_status_and_result(db_session):
    """AsyncJobService._finish updates job to done with result_json."""
    job = await AsyncJobService.create(db_session, "tailor_analyse")
    await db_session.commit()

    await AsyncJobService._finish(job.id, '{"key": "value"}', None, db=db_session)

    refreshed = await AsyncJobService.get(db_session, job.id)
    assert refreshed is not None
    assert refreshed.status == "done"
    assert refreshed.result_json == '{"key": "value"}'
    assert refreshed.error is None


@pytest.mark.asyncio
async def test_finish_sets_failed_status_on_error(db_session):
    """AsyncJobService._finish with error string sets status=failed."""
    job = await AsyncJobService.create(db_session, "coach_session")
    await db_session.commit()

    await AsyncJobService._finish(job.id, None, "LLM timeout", db=db_session)

    refreshed = await AsyncJobService.get(db_session, job.id)
    assert refreshed is not None
    assert refreshed.status == "failed"
    assert refreshed.error == "LLM timeout"
    assert refreshed.result_json is None


@pytest.mark.asyncio
async def test_get_returns_none_for_unknown_id(db_session):
    """AsyncJobService.get returns None for a non-existent job ID."""
    result = await AsyncJobService.get(db_session, "no-such-id")
    assert result is None


@pytest.mark.asyncio
async def test_list_completed_since_returns_recent_done_jobs(db_session):
    """list_completed_since returns done jobs created after the given datetime."""
    job1 = await AsyncJobService.create(db_session, "ghost_analyse")
    job2 = await AsyncJobService.create(db_session, "email_generate")
    await db_session.commit()

    cutoff = datetime.utcnow() - timedelta(seconds=5)

    await AsyncJobService._finish(job1.id, '{}', None, db=db_session)
    await AsyncJobService._finish(job2.id, '{}', None, db=db_session)

    results = await AsyncJobService.list_completed_since(db_session, cutoff, limit=10)
    ids = [r.id for r in results]
    assert job1.id in ids
    assert job2.id in ids


def test_cancelled_job_has_useful_error_message():
    assert _error_message(asyncio.CancelledError()) == "Server stopped while the job was in progress"
