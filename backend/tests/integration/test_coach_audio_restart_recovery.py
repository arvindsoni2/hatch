"""V6 Scenario F: a crashed audio worker recovers without a second attempt."""

import asyncio
import base64
import hashlib
import os
import signal
from datetime import datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import create_sqlite_engine
from app.models.async_job import AsyncJob
from app.models.coach_session import InterviewAttemptEvaluation, SessionRecording
from coach_app_process import CoachAppProcess
from test_coach_degraded_ai_journey import (
    ANSWER,
    AUDIO_FIXTURE,
    _command,
    _live,
    _wait_for_setup,
)


class ShortDeadlineCoachAppProcess(CoachAppProcess):
    def _environment(self):
        return super()._environment() | {
            "HATCH_COACH_TIMEOUT_CONVERSATIONAL_JOB_SECONDS": "60"
        }


@pytest.mark.asyncio
async def test_audio_crash_then_startup_recovery_preserves_one_attempt(tmp_path):
    """An expired crashed generation becomes retryable; retry reuses its attempt."""
    database_path = tmp_path / "audio-restart.db"
    async with ShortDeadlineCoachAppProcess(
        database_path,
        tmp_path / "media",
        app_module="coach_restart_audio_test_server:app",
    ) as app_process:
        async with httpx.AsyncClient(timeout=5) as client:
            created = await client.post(
                f"{app_process.base_url}/api/coach/sessions",
                json={
                    "company_name": "Synthetic Restart Co",
                    "role_title": "Engineer",
                    "jd_text": "Build reliable software.",
                    "experience_version": "conversational_v1",
                    "conversational_config": {
                        "interview_type": "mixed",
                        "difficulty": "realistic",
                        "duration_minutes": 30,
                        "planned_question_count": 6,
                        "role_family": "software_engineering",
                        "role_level": "senior",
                        "industry": "technology",
                        "locale": "en-GB",
                        "focus_areas": ["delivery_execution"],
                        "allowed_answer_modes": ["text", "audio"],
                        "evidence_selection": {
                            "application_cv": "none",
                            "master_cv": "exclude",
                            "question_bank": "exclude",
                            "company_research": "exclude",
                            "draft_evidence_consent": False,
                        },
                    },
                },
            )
            assert created.status_code == 202, created.text
            session_id = created.json()["session_id"]
            await _wait_for_setup(client, app_process.base_url, created.json()["job_id"])
            await _command(client, app_process.base_url, session_id, "start", {})
            begun = await _command(
                client,
                app_process.base_url,
                session_id,
                "begin_answer",
                {"recording_type": "audio", "client_attempt_id": str(uuid4())},
            )
            attempt_id = begun["active_attempt_id"]
            audio = base64.b64decode(AUDIO_FIXTURE.read_text(encoding="ascii"))
            upload_id = str(uuid4())
            uploaded = await client.post(
                f"{app_process.base_url}/api/coach/sessions/{session_id}/attempts/{attempt_id}/audio",
                data={"upload_id": upload_id, "content_sha256": hashlib.sha256(audio).hexdigest()},
                files={"audio": ("synthetic-tone.webm", audio, "audio/webm")},
            )
            assert uploaded.status_code == 200, uploaded.text
            finished = await _command(
                client,
                app_process.base_url,
                session_id,
                "finish_answer",
                {"attempt_id": attempt_id, "upload_id": upload_id},
            )
            first_job_id = finished["async_job_id"]
            async with asyncio.timeout(20):
                while not (tmp_path / "restart-transcription-entered").exists():
                    await asyncio.sleep(0.05)

            engine = create_sqlite_engine(f"sqlite+aiosqlite:///{database_path}")
            factory = async_sessionmaker(engine, expire_on_commit=False)
            try:
                async with factory() as db:
                    attempt = await db.get(SessionRecording, attempt_id)
                    assert attempt is not None
                    evaluation = await db.scalar(
                        select(InterviewAttemptEvaluation).where(
                            InterviewAttemptEvaluation.recording_id == attempt_id,
                            InterviewAttemptEvaluation.async_job_id == first_job_id,
                            InterviewAttemptEvaluation.state == "pending",
                        )
                    )
                    assert evaluation is not None
                    deadline = datetime.fromisoformat(
                        evaluation.diagnostics_json["processing_claim"]["job_deadline_at"]
                    )
                    assert attempt.processing_generation == 1
                    assert attempt.processing_retry_count == 0
                    assert (await db.get(AsyncJob, first_job_id)).status in {
                        "pending", "running"
                    }
                    assert await db.scalar(
                        select(func.count(SessionRecording.id)).where(
                            SessionRecording.session_id == session_id
                        )
                    ) == 1

                crashed_pid = app_process.pid
                os.kill(crashed_pid, signal.SIGKILL)
                assert app_process._process is not None
                await asyncio.wait_for(app_process._process.wait(), timeout=5)
                assert app_process._process.returncode != 0

                # The application must not mark an in-deadline claim stale.
                # Advance real time only to its contract deadline, then boot a new PID.
                wait_seconds = max(0, (deadline - datetime.utcnow()).total_seconds()) + 0.5
                async with asyncio.timeout(65):
                    await asyncio.sleep(wait_seconds)
                (tmp_path / "allow-restart-transcription").touch()
                await app_process.restart()
                assert app_process.pid != crashed_pid

                live = await _live(client, app_process.base_url, session_id)
                assert live["conversation_state"] == "recoverable_error"
                assert live["active_attempt"]["id"] == attempt_id
                assert live["active_attempt"]["processing_retry_count"] == 0
                assert "retry_processing" in live["allowed_commands"]
                async with factory() as db:
                    first_job = await db.get(AsyncJob, first_job_id)
                    assert first_job is not None and first_job.status == "failed"
                    assert await db.scalar(
                        select(func.count(SessionRecording.id)).where(
                            SessionRecording.session_id == session_id
                        )
                    ) == 1

                retried = await _command(
                    client, app_process.base_url, session_id, "retry_processing", {}
                )
                assert retried["async_job_id"] != first_job_id
                async with asyncio.timeout(30):
                    while True:
                        live = await _live(client, app_process.base_url, session_id)
                        if live["conversation_state"] == "awaiting_next_action":
                            break
                        await asyncio.sleep(0.1)
                assert live["active_attempt"]["id"] == attempt_id
                assert live["active_attempt"]["transcript_version"]["transcript"] == ANSWER
                assert live["answer_review"]["evaluation_state"] == "completed"
                async with factory() as db:
                    attempt = await db.get(SessionRecording, attempt_id)
                    assert attempt.processing_generation == 2
                    assert attempt.processing_retry_count == 1
                    assert await db.scalar(
                        select(func.count(SessionRecording.id)).where(
                            SessionRecording.session_id == session_id
                        )
                    ) == 1
            finally:
                await engine.dispose()
    log_text = (tmp_path / "coach-app-process.log").read_text(encoding="utf-8")
    assert ANSWER not in log_text
    assert "openai._base_client" not in log_text
