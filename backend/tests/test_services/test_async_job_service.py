"""Tests for AsyncJobService."""

from __future__ import annotations

from datetime import datetime, timedelta
from contextlib import contextmanager

import pytest

import asyncio

from app.services.async_job_service import AsyncJobService, _error_message
from app.observability import TraceContextToken


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

    await AsyncJobService._finish(job1.id, "{}", None, db=db_session)
    await AsyncJobService._finish(job2.id, "{}", None, db=db_session)

    results = await AsyncJobService.list_completed_since(db_session, cutoff, limit=10)
    ids = [r.id for r in results]
    assert job1.id in ids
    assert job2.id in ids


def test_cancelled_job_has_useful_error_message():
    assert (
        _error_message(asyncio.CancelledError())
        == "Server stopped while the job was in progress"
    )


@pytest.mark.asyncio
async def test_run_activates_trace_context_and_records_terminal_outcome(
    db_session,
    monkeypatch,
):
    from app import database
    from app.services import async_job_service

    job = await AsyncJobService.create(db_session, "coach_session")
    await db_session.commit()
    entered: list[tuple[TraceContextToken, dict[str, str]]] = []
    outcomes: list[tuple[str, str, dict[str, str]]] = []
    completed = asyncio.Event()
    token = TraceContextToken()

    class _SessionContext:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *_args):
            return False

    class _Telemetry:
        @contextmanager
        def use_background_trace_context(self, trace_context, attributes=None):
            entered.append((trace_context, dict(attributes or {})))
            yield

        def record_coach_outcome(self, family, outcome, attributes=None):
            outcomes.append((family, outcome, dict(attributes or {})))

    monkeypatch.setattr(database, "AsyncSessionLocal", _SessionContext)
    monkeypatch.setattr(
        async_job_service,
        "get_telemetry",
        lambda: _Telemetry(),
        raising=False,
    )

    async def _work() -> None:
        await AsyncJobService._finish(job.id, "{}", None, db=db_session)
        completed.set()

    AsyncJobService.run(
        job.id,
        _work(),
        trace_context=token,
        trace_attributes={
            "hatch.coach.session_id": "session-1",
            "hatch.async_job_id": job.id,
        },
        telemetry_operation="session_create",
    )
    await asyncio.wait_for(completed.wait(), timeout=1)
    await asyncio.sleep(0)

    assert entered == [
        (
            token,
            {
                "hatch.coach.session_id": "session-1",
                "hatch.async_job_id": job.id,
            },
        )
    ]
    assert outcomes == [
        (
            "async_job",
            "done",
            {"hatch.coach.operation": "session_create"},
        )
    ]
