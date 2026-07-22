"""Tests that coach endpoints return 202 + job_id."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.models.async_job import AsyncJob
from app.models.coach_session import InterviewSession, SessionQuestion, SessionRecording
from app.repositories.session_repository import SessionRepository


async def _seed_active_question(db_session, session_id: str, question_id: str) -> None:
    db_session.add(
        InterviewSession(
            id=session_id,
            company_name="Acme Corp",
            role_title="Senior Developer",
            config={"question_count": 1},
            status="active",
        )
    )
    db_session.add(
        SessionQuestion(
            id=question_id,
            session_id=session_id,
            question_num=1,
            text="Tell me about a delivery challenge.",
            category="Behavioural",
            difficulty="medium",
            order_in_session=1,
        )
    )
    await db_session.commit()


# ---------------------------------------------------------------------------
# Existing session/answer async tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_session_returns_202(client):
    """POST /api/coach/sessions returns 202 with job_id."""
    response = await client.post(
        "/api/coach/sessions",
        json={
            "company_name": "Acme Corp",
            "role_title": "Senior Developer",
            "config": {
                "question_count": 5,
                "categories": ["Technical"],
                "recording_mode": "text",
                "difficulty": "medium",
            },
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "coach_session"


@pytest.mark.asyncio
async def test_submit_answer_returns_202(client, db_session):
    """POST /api/coach/sessions/{id}/submit-answer returns 202 with job_id."""
    await _seed_active_question(db_session, "session-1", "question-1")
    with patch("app.routers.coach.AsyncJobService.run") as run:
        response = await client.post(
            "/api/coach/sessions/session-1/submit-answer",
            params={"question_id": "question-1"},
            json={"transcript": "I led a team...", "duration_ms": 45000},
        )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "submit_answer"
    recording = (
        await db_session.execute(select(SessionRecording))
    ).scalar_one()
    assert recording.evaluation_state == "pending"
    assert recording.async_job_id == data["job_id"]
    session = (
        await db_session.execute(
            select(InterviewSession).where(InterviewSession.id == "session-1")
        )
    ).scalar_one()
    assert session.activity_version == 1
    run.assert_called_once()
    run.call_args.args[1].close()


@pytest.mark.asyncio
async def test_whitespace_text_submission_returns_422_without_job_or_recording(
    client, db_session
):
    await _seed_active_question(db_session, "session-empty", "question-empty")

    response = await client.post(
        "/api/coach/sessions/session-empty/submit-answer",
        params={"question_id": "question-empty"},
        json={"transcript": "   "},
    )

    assert response.status_code == 422
    assert (await db_session.execute(select(AsyncJob))).scalars().all() == []
    assert (await db_session.execute(select(SessionRecording))).scalars().all() == []


@pytest.mark.asyncio
async def test_repeated_submissions_reserve_immutable_attempts(client, db_session):
    await _seed_active_question(db_session, "session-repeat", "question-repeat")
    with patch("app.routers.coach.AsyncJobService.run") as run:
        first = await client.post(
            "/api/coach/sessions/session-repeat/submit-answer",
            params={"question_id": "question-repeat"},
            json={"transcript": "First answer"},
        )
        second = await client.post(
            "/api/coach/sessions/session-repeat/submit-answer",
            params={"question_id": "question-repeat"},
            json={"transcript": "Second answer"},
        )

    assert first.status_code == second.status_code == 202
    recordings = (
        await db_session.execute(select(SessionRecording).order_by(SessionRecording.id))
    ).scalars().all()
    assert len(recordings) == 2
    assert {recording.async_job_id for recording in recordings} == {
        first.json()["job_id"],
        second.json()["job_id"],
    }
    for call in run.call_args_list:
        call.args[1].close()


@pytest.mark.asyncio
async def test_submit_after_report_claim_returns_machine_code_409(client, db_session):
    await _seed_active_question(db_session, "session-closed", "question-closed")
    session = (
        await db_session.execute(
            select(InterviewSession).where(InterviewSession.id == "session-closed")
        )
    ).scalar_one()
    session.report_state = "building"
    await db_session.commit()

    response = await client.post(
        "/api/coach/sessions/session-closed/submit-answer",
        params={"question_id": "question-closed"},
        json={"transcript": "Late answer"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "coach_session_closed"
    assert (await db_session.execute(select(SessionRecording))).scalars().all() == []


@pytest.mark.asyncio
async def test_fenced_answer_finalisation_requires_job_and_pending_state(db_session):
    await _seed_active_question(db_session, "session-fence", "question-fence")
    job = AsyncJob(type="submit_answer")
    db_session.add(job)
    await db_session.flush()
    repo = SessionRepository(db_session)
    recording = await repo.reserve_answer_attempt(
        session_id="session-fence",
        question_id="question-fence",
        async_job_id=job.id,
        recording_type="text",
        transcript="Answer",
    )
    await db_session.commit()

    wrong_job = await repo.finalize_answer_attempt(
        recording.id,
        "other-job",
        evaluation_state="completed",
        evaluation_json='{"overall": 8}',
    )
    recording.evaluation_state = "failed"
    await db_session.commit()
    reconciled = await repo.finalize_answer_attempt(
        recording.id,
        job.id,
        evaluation_state="completed",
        evaluation_json='{"overall": 8}',
    )

    assert wrong_job is False
    assert reconciled is False


@pytest.mark.asyncio
async def test_end_session_returns_202(client):
    """POST /api/coach/sessions/{id}/end returns 202 with job_id."""
    response = await client.post("/api/coach/sessions/fake-session-id/end")
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "end_session"


# ---------------------------------------------------------------------------
# Phase A Task 4 — submit-audio endpoint
# ---------------------------------------------------------------------------

# Minimal valid WAV: RIFF header + WAVE marker (no audio data; just needs to be readable)
_WAV_HEADER = (
    b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00"
    b"\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00"
    b"data\x00\x00\x00\x00"
)


@pytest.mark.asyncio
async def test_submit_audio_returns_202(client, db_session, tmp_path, monkeypatch):
    """POST /api/coach/sessions/{id}/submit-audio returns 202 with job_id and type."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    await _seed_active_question(db_session, "s-audio-test", "q-audio-001")
    with patch("app.routers.coach.AsyncJobService.run") as run:
        response = await client.post(
            "/api/coach/sessions/s-audio-test/submit-audio",
            files={"audio": ("answer.wav", _WAV_HEADER, "audio/wav")},
            data={"question_id": "q-audio-001"},
        )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "submit_audio"
    recording = (
        await db_session.execute(select(SessionRecording))
    ).scalar_one()
    assert recording.evaluation_state == "pending"
    assert recording.async_job_id == data["job_id"]
    assert data["job_id"] in (recording.audio_uri or "")
    run.call_args.args[1].close()


@pytest.mark.asyncio
async def test_submit_audio_rejects_non_audio_content_type(client, tmp_path, monkeypatch):
    """POST /api/coach/sessions/{id}/submit-audio returns 400 for non-audio content-type."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    response = await client.post(
        "/api/coach/sessions/s-audio-test/submit-audio",
        files={"audio": ("answer.txt", b"plain text content", "text/plain")},
        data={"question_id": "q-audio-001"},
    )
    assert response.status_code == 400
    assert "Audio files only" in response.json()["detail"]


@pytest.mark.asyncio
async def test_submit_audio_saves_file_to_recordings_dir(
    client, db_session, tmp_path, monkeypatch
):
    """POST /api/coach/sessions/{id}/submit-audio saves the audio blob to recordings/{session}/{question}.ext."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    await _seed_active_question(db_session, "s123", "q456")
    with patch("app.routers.coach.AsyncJobService.run") as run:
        response = await client.post(
            "/api/coach/sessions/s123/submit-audio",
            files={"audio": ("answer.wav", _WAV_HEADER, "audio/wav")},
            data={"question_id": "q456"},
        )
    assert response.status_code == 202
    saved = (
        tmp_path
        / "recordings"
        / "s123"
        / f"q456-{response.json()['job_id']}.wav"
    )
    assert saved.exists(), f"Expected saved audio at {saved}"
    assert saved.read_bytes() == _WAV_HEADER
    run.call_args.args[1].close()


@pytest.mark.asyncio
async def test_skip_is_terminal_and_increments_activity(client, db_session):
    await _seed_active_question(db_session, "session-skip", "question-skip")

    response = await client.post(
        "/api/coach/sessions/session-skip/skip",
        params={"question_id": "question-skip"},
    )

    assert response.status_code == 204
    recording = (
        await db_session.execute(select(SessionRecording))
    ).scalar_one()
    assert recording.evaluation_state == "skipped"
    assert recording.async_job_id is None
    session = (
        await db_session.execute(
            select(InterviewSession).where(InterviewSession.id == "session-skip")
        )
    ).scalar_one()
    assert session.activity_version == 1
