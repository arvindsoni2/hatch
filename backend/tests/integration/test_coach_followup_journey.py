"""V6 Scenario D through real HTTP dispatch and persisted questions."""

import asyncio
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import create_sqlite_engine
from app.models.coach_session import (
    InterviewAttemptEvaluation,
    SessionQuestion,
    SessionRecording,
)
from coach_app_process import CoachAppProcess
from test_coach_degraded_ai_journey import _command, _live, _wait_for_setup


ROOT = "I led the migration and stakeholders were satisfied."
RESULT = "We cut deployment time by three hours."
ACTION = "I personally automated deployment checks."


async def _submit_and_accept(client, base_url, session_id, answer):
    begun = await _command(
        client,
        base_url,
        session_id,
        "begin_answer",
        {"recording_type": "text", "client_attempt_id": str(uuid4())},
    )
    attempt_id = begun["active_attempt_id"]
    await _command(
        client,
        base_url,
        session_id,
        "finish_answer",
        {"attempt_id": attempt_id, "transcript": answer},
    )
    async with asyncio.timeout(30):
        while True:
            live = await _live(client, base_url, session_id)
            if live["conversation_state"] == "awaiting_next_action":
                break
            await asyncio.sleep(0.1)
    assert live["answer_review"]["evaluation_state"] == "completed"
    await _command(client, base_url, session_id, "accept_attempt", {"attempt_id": attempt_id})
    return await _live(client, base_url, session_id)


@pytest.mark.asyncio
async def test_two_grounded_followups_then_planned_sequence_resumes(tmp_path):
    """Losing admission or the cap changes the persisted question sequence."""
    database_path = tmp_path / "followups.db"
    async with CoachAppProcess(
        database_path,
        tmp_path / "media",
        app_module="coach_followup_test_server:app",
    ) as app_process:
        base_url = app_process.base_url
        async with httpx.AsyncClient(timeout=5) as client:
            created = await client.post(
                f"{base_url}/api/coach/sessions",
                json={
                    "company_name": "Synthetic Follow-up Co",
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
                        "allowed_answer_modes": ["text"],
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
            await _wait_for_setup(client, base_url, created.json()["job_id"])
            await _command(client, base_url, session_id, "start", {})
            root_id = (await _live(client, base_url, session_id))["active_question"]["id"]

            first = await _submit_and_accept(client, base_url, session_id, ROOT)
            assert first["active_question"]["question_kind"] == "adaptive_follow_up"
            assert first["active_question"]["follow_up_depth"] == 1
            assert first["active_question"]["follow_up_reason"] == "measurable_result"
            first_id = first["active_question"]["id"]

            second = await _submit_and_accept(client, base_url, session_id, RESULT)
            assert second["active_question"]["question_kind"] == "adaptive_follow_up"
            assert second["active_question"]["follow_up_depth"] == 2
            assert second["active_question"]["follow_up_reason"] == "personal_action"
            second_id = second["active_question"]["id"]

            resumed = await _submit_and_accept(client, base_url, session_id, ACTION)
            assert resumed["active_question"]["question_kind"] == "planned"
            assert resumed["active_question"]["id"] not in {root_id, first_id, second_id}
            assert resumed["progress"]["follow_ups_completed"] == 2
            assert resumed["progress"]["planned_questions_completed"] == 1

        engine = create_sqlite_engine(f"sqlite+aiosqlite:///{database_path}")
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as db:
                followups = list(
                    (await db.scalars(
                        select(SessionQuestion)
                        .where(
                            SessionQuestion.session_id == session_id,
                            SessionQuestion.question_kind == "adaptive_follow_up",
                        )
                        .order_by(SessionQuestion.follow_up_depth)
                    )).all()
                )
                assert [question.id for question in followups] == [first_id, second_id]
                assert [question.parent_question_id for question in followups] == [root_id, first_id]
                assert all(question.root_question_id == root_id for question in followups)
                last_attempt = await db.scalar(
                    select(SessionRecording).where(
                        SessionRecording.question_id == second_id,
                        SessionRecording.accepted_at.is_not(None),
                    )
                )
                assert last_attempt is not None
                last_evaluation = await db.get(
                    InterviewAttemptEvaluation,
                    last_attempt.current_evaluation_version_id,
                )
                assert last_evaluation is not None
                assert last_evaluation.follow_up_proposal_json["should_ask"] is True
        finally:
            await engine.dispose()
    log_text = (tmp_path / "coach-app-process.log").read_text(encoding="utf-8")
    assert "openai._base_client" not in log_text
    assert all(answer not in log_text for answer in (ROOT, RESULT, ACTION))
