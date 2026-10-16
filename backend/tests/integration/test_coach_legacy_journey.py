"""V6 Scenario H: legacy Coach remains a complete, separate product path."""

import asyncio

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import create_sqlite_engine
from app.models.coach_session import (
    InterviewAttemptEvaluation,
    InterviewSession,
    InterviewTranscriptVersion,
    SessionQuestion,
    SessionRecording,
)
from app.schemas.coach import SessionFeedbackReport

from coach_app_process import CoachAppProcess


async def _wait_for_job(client: httpx.AsyncClient, base_url: str, job_id: str) -> dict:
    async with asyncio.timeout(30):
        while True:
            response = await client.get(f"{base_url}/api/async-jobs/{job_id}")
            assert response.status_code == 200
            job = response.json()
            if job["status"] in {"done", "failed"}:
                return job
            await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_real_legacy_open_submit_end_report_preserves_numeric_contract(tmp_path):
    """Wrong experience dispatch or conversational writes fail this journey."""
    database_path = tmp_path / "legacy-journey.db"
    async with CoachAppProcess(
        database_path, tmp_path / "media", app_module="coach_legacy_test_server:app"
    ) as app_process:
        engine = create_sqlite_engine(f"sqlite+aiosqlite:///{database_path}")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as db:
                db.add(
                    InterviewSession(
                        id="legacy-journey",
                        company_name="Synthetic Legacy Co",
                        role_title="Engineer",
                        config={"question_count": 1},
                        status="active",
                        experience_version="legacy_v1",
                    )
                )
                db.add(
                    SessionQuestion(
                        id="legacy-question",
                        session_id="legacy-journey",
                        question_num=1,
                        text="Describe a delivery challenge you solved.",
                        category="Behavioural",
                        order_in_session=1,
                    )
                )
                await db.commit()

            async with httpx.AsyncClient(timeout=5) as client:
                opened = await client.get(
                    f"{app_process.base_url}/api/coach/sessions/legacy-journey"
                )
                assert opened.status_code == 200
                assert opened.json()["questions"][0]["id"] == "legacy-question"

                submitted = await client.post(
                    f"{app_process.base_url}/api/coach/sessions/legacy-journey/submit-answer",
                    params={"question_id": "legacy-question"},
                    json={
                        "transcript": "I coordinated a synthetic migration and resolved a release blocker.",
                        "duration_ms": 1_000,
                    },
                )
                assert submitted.status_code == 202, submitted.text
                answer_job = await _wait_for_job(
                    client, app_process.base_url, submitted.json()["job_id"]
                )
                assert answer_job["status"] == "done", answer_job

                ended = await client.post(
                    f"{app_process.base_url}/api/coach/sessions/legacy-journey/end"
                )
                assert ended.status_code == 202, ended.text
                report_job = await _wait_for_job(
                    client, app_process.base_url, ended.json()["job_id"]
                )
                assert report_job["status"] == "done", report_job

                response = await client.get(
                    f"{app_process.base_url}/api/coach/sessions/legacy-journey/report"
                )
                assert response.status_code == 200
                report = SessionFeedbackReport.model_validate(response.json())
                assert report.session_id == "legacy-journey"
                assert report.question_count_total == 1
                assert report.question_count_evaluated == 1
                assert report.overall_score == 7.0
                assert "session_level" not in response.json()

            async with factory() as db:
                session = await db.get(InterviewSession, "legacy-journey")
                assert session is not None
                assert session.experience_version == "legacy_v1"
                assert session.report_json == response.json()
                assert await db.scalar(
                    select(func.count(SessionRecording.id)).where(
                        SessionRecording.session_id == session.id
                    )
                ) == 1
                assert await db.scalar(select(func.count(InterviewTranscriptVersion.id))) == 0
                assert await db.scalar(select(func.count(InterviewAttemptEvaluation.id))) == 0
        finally:
            await engine.dispose()
    log_text = (tmp_path / "coach-app-process.log").read_text(encoding="utf-8")
    assert "openai._base_client" not in log_text
