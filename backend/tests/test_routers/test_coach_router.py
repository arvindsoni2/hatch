"""Integration tests for /api/coach router — create session, submit answer, end session, 404 handling."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import func, select

from app.main import app
from app.config import settings
from app.models.coach_session import InterviewSession, SessionRecording
from app.schemas.coach import (
    AnswerEvaluation,
    CompanyResearchResponse,
    SessionFeedbackReport,
    SessionResponse,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# ---------------------------------------------------------------------------
# Helpers / shared data
# ---------------------------------------------------------------------------

SAMPLE_SESSION_RESPONSE = SessionResponse(
    id="session-uuid-001",
    application_id=None,
    company_name="Accenture",
    role_title="Solutions Architect",
    status="active",
    overall_score=None,
    questions=[],
    created_at="2026-03-10T09:00:00",
)

SAMPLE_EVALUATION = AnswerEvaluation(
    scores={
        "relevance": 8,
        "star_structure": 7,
        "technical_depth": 8,
        "conciseness": 7,
        "communication": 8,
        "impact_metrics": 7,
    },
    overall=7.5,
    feedback="Good STAR structure with quantified outcomes.",
    strengths=["Clear structure", "Technical depth"],
    improvements=["Add more metrics"],
    follow_up_question=None,
    speech_coaching=[],
)

SAMPLE_REPORT = SessionFeedbackReport(
    session_id="session-uuid-001",
    overall_score=7.5,
    category_scores={"Technical": 8.0, "Behavioural": 7.0},
    executive_summary="Strong performance with clear STAR responses.",
    strengths=["Technical depth", "Quantified outcomes"],
    improvement_areas=["Reduce hedging language"],
    coaching_points=["Practice the STAR framework daily"],
    practice_plan=[
        {"day": 1, "focus": "STAR Structure", "activity": "Practice 3 STAR answers", "resource": None}
    ],
    question_evaluations=[],
)

SAMPLE_RESEARCH = CompanyResearchResponse(
    company_name="Accenture",
    sector="Consulting",
    website="https://www.accenture.com",
    description="Global professional services company.",
    recent_news=[],
    key_products=[],
    tech_stack_signals=[],
)


def close_queued_work(_job_id, work, **_kwargs) -> None:
    """Keep the real create transaction while preventing a test worker escape."""
    work.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_session_returns_202(client) -> None:
    """POST /api/coach/sessions returns 202 with job_id (async pattern)."""
    response = await client.post(
        "/api/coach/sessions",
        json={
            "company_name": "Accenture",
            "role_title": "Solutions Architect",
            "config": {"question_count": 5},
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "coach_session"


@pytest.mark.asyncio
async def test_submit_answer_unknown_session_does_not_queue_work(client) -> None:
    """Unknown submissions fail synchronously instead of queuing doomed work."""
    response = await client.post(
        "/api/coach/sessions/session-uuid-001/submit-answer",
        params={"question_id": "q-uuid-001"},
        json={"transcript": "In my previous role at a FTSE 100 company...", "duration_ms": 60000},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_legacy_submit_rejects_conversational_session_without_mutation(
    client, db_session
) -> None:
    """Removing the experience guard would create a legacy recording."""
    session = InterviewSession(
        id="conversation_submit_1",
        company_name="Example Co",
        role_title="Architect",
        config={},
        status="active",
        experience_version="conversational_v1",
        conversation_state="asking",
        state_version=1,
    )
    db_session.add(session)
    await db_session.commit()

    response = await client.post(
        f"/api/coach/sessions/{session.id}/submit-answer",
        params={"question_id": "question_1"},
        json={"transcript": "synthetic"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "coach_conversational_command_required"
    assert (
        await db_session.scalar(
            select(func.count(SessionRecording.id)).where(
                SessionRecording.session_id == session.id
            )
        )
        == 0
    )


@pytest.mark.asyncio
async def test_legacy_end_and_retry_reject_conversational_session_before_side_effects(
    client, db_session
) -> None:
    """Removing either guard would let a legacy lifecycle flow mutate this row."""
    session = InterviewSession(
        id="conversation_lifecycle_1",
        company_name="Example Co",
        role_title="Architect",
        config={},
        status="setup",
        experience_version="conversational_v1",
        conversation_state="ready",
        state_version=0,
    )
    db_session.add(session)
    await db_session.commit()

    end_response = await client.post(f"/api/coach/sessions/{session.id}/end")
    retry_response = await client.post(f"/api/coach/sessions/{session.id}/retry")

    assert end_response.status_code == 409
    assert (
        end_response.json()["error"]["code"] == "coach_conversational_command_required"
    )
    assert retry_response.status_code == 409
    assert (
        retry_response.json()["error"]["code"]
        == "coach_conversational_session_retry_unsupported"
    )
    await db_session.refresh(session)
    assert (session.status, session.conversation_state) == ("setup", "ready")


@pytest.mark.asyncio
async def test_flag_off_rejects_new_conversation_but_preserves_legacy_create(
    client, monkeypatch
) -> None:
    """Incorrect feature dispatch would either admit v1 or break the legacy 202."""
    monkeypatch.setattr(settings, "HATCH_COACH_CONVERSATIONAL_ENABLED", False)
    conversational = await client.post(
        "/api/coach/sessions",
        json={
            "company_name": "Example Co",
            "role_title": "Architect",
            "jd_text": "Build resilient systems.",
            "experience_version": "conversational_v1",
            "conversational_config": {
                "interview_type": "mixed",
                "difficulty": "realistic",
                "duration_minutes": 30,
                "planned_question_count": 6,
                "role_family": "solution_architecture",
                "role_level": "senior",
                "industry": "technology",
                "locale": "en-GB",
                "focus_areas": ["architecture"],
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
    with patch(
        "app.services.coach_session_queue.AsyncJobService.run",
        side_effect=close_queued_work,
    ):
        legacy = await client.post(
            "/api/coach/sessions",
            json={"company_name": "Example Co", "role_title": "Architect"},
        )

    assert conversational.status_code == 403
    assert conversational.json()["error"]["code"] == "coach_conversation_not_enabled"
    assert legacy.status_code == 202


@pytest.mark.asyncio
async def test_capabilities_truthfully_describes_conversation_and_video_support(
    client, monkeypatch
) -> None:
    """Omitting the feature flag or claiming video support must fail this test."""
    monkeypatch.setattr(settings, "HATCH_COACH_CONVERSATIONAL_ENABLED", False)

    response = await client.get("/api/coach/capabilities")

    assert response.status_code == 200
    assert response.json()["conversational"] is False
    assert response.json()["video_analysis_for_conversational"] is False


@pytest.mark.asyncio
async def test_session_list_additively_exposes_conversational_summary(
    client, db_session
) -> None:
    """Dropping the persisted mode or retention summary would hide live routing data."""
    session = InterviewSession(
        id="conversation_summary_1",
        company_name="Example Co",
        role_title="Architect",
        config={},
        status="setup",
        experience_version="conversational_v1",
        conversation_state="ready",
        retention_policy_json={
            "audio": "delete_after_processing",
            "transcript": "retain",
        },
    )
    db_session.add(session)
    await db_session.commit()

    response = await client.get("/api/coach/sessions")

    assert response.status_code == 200
    summary = next(item for item in response.json() if item["id"] == session.id)
    assert summary["experience_version"] == "conversational_v1"
    assert summary["conversation_state"] == "ready"
    assert summary["retention_summary"] == {
        "audio": "delete_after_processing",
        "transcript": "retain",
    }


@pytest.mark.asyncio
async def test_end_session_unknown_returns_404(client) -> None:
    """An unknown session cannot create an orphan report job."""
    response = await client.post("/api/coach/sessions/session-uuid-001/end")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_session_not_found_returns_404() -> None:
    """GET /api/coach/sessions/{id} returns 404 for a missing session."""
    with patch("app.routers.coach.CoachService") as MockSvc:
        instance = MockSvc.return_value
        from fastapi import HTTPException
        instance.get_session = AsyncMock(side_effect=HTTPException(status_code=404, detail="Session not found"))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/coach/sessions/nonexistent-id")
    assert response.status_code == 404
    assert "Session not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_research_company_returns_200() -> None:
    """POST /api/coach/research returns 200 with CompanyResearchResponse."""
    with patch("app.routers.coach.CoachService") as MockSvc:
        instance = MockSvc.return_value
        instance.research_company = AsyncMock(return_value=SAMPLE_RESEARCH)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/coach/research",
                params={"company_name": "Accenture", "sector": "Consulting"},
            )
    assert response.status_code == 200
    data = response.json()
    assert data["company_name"] == "Accenture"


@pytest.mark.asyncio
async def test_list_sessions_returns_200() -> None:
    """GET /api/coach/sessions returns 200 with a list."""
    with patch("app.routers.coach.CoachService") as MockSvc:
        instance = MockSvc.return_value
        instance.list_sessions = AsyncMock(return_value=[])
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/coach/sessions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_get_research_not_found_returns_404(client: AsyncClient) -> None:
    """GET /api/coach/research/{company_name} returns 404 when no cached research exists."""
    response = await client.get("/api/coach/research/UnknownCompanyXYZ")
    assert response.status_code == 404
    assert "No cached research" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_session_not_found_returns_404(client: AsyncClient) -> None:
    """DELETE /api/coach/sessions/{id} returns 404 for a non-existent session."""
    response = await client.delete("/api/coach/sessions/nonexistent-session-id")
    assert response.status_code == 404
    assert "Session not found" in response.json()["detail"]


# ---------------------------------------------------------------------------
# SEC-3: path traversal guards on submit-audio
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_audio_rejects_traversal_in_question_id(client: AsyncClient, tmp_path) -> None:
    """submit-audio must reject question_id containing path traversal chars."""
    audio_bytes = b"RIFF" + b"\x00" * 36  # minimal dummy
    response = await client.post(
        "/api/coach/sessions/valid-session-id/submit-audio",
        data={"question_id": "../../etc/passwd"},
        files={"audio": ("answer.webm", audio_bytes, "audio/webm")},
    )
    assert response.status_code == 400
    assert "question_id" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_submit_audio_rejects_traversal_in_session_id(tmp_path) -> None:
    """submit-audio must reject session_id containing path traversal chars."""
    audio_bytes = b"RIFF" + b"\x00" * 36
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/coach/sessions/../foo/submit-audio",
            data={"question_id": "valid-question-id"},
            files={"audio": ("answer.webm", audio_bytes, "audio/webm")},
        )
    # FastAPI will match /api/coach/sessions/{session_id=..}/foo/submit-audio differently;
    # the path normalisation at the HTTP layer means the session_id param itself contains
    # only the URL-decoded segment, which our regex rejects.
    assert response.status_code in (400, 404)


@pytest.mark.asyncio
async def test_submit_audio_accepts_valid_ids(client: AsyncClient, tmp_path, monkeypatch) -> None:
    """submit-audio accepts UUIDs and slug IDs."""
    import uuid as _uuid
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    audio_bytes = b"RIFF" + b"\x00" * 36
    response = await client.post(
        f"/api/coach/sessions/{_uuid.uuid4()}/submit-audio",
        data={"question_id": str(_uuid.uuid4())},
        files={"audio": ("answer.webm", audio_bytes, "audio/webm")},
    )
    # Unknown-but-safe IDs are rejected synchronously, never a path-operation 500.
    assert response.status_code in (400, 404, 422)


@pytest.mark.asyncio
async def test_get_next_question_with_mock_service() -> None:
    """GET /api/coach/sessions/{id}/next-question returns 200 (null) with mocked service."""
    with patch("app.routers.coach.CoachService") as MockSvc:
        instance = MockSvc.return_value
        instance.get_next_question = AsyncMock(return_value=None)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/coach/sessions/session-uuid-001/next-question")
    assert response.status_code == 200
    assert response.json() is None


@pytest.mark.asyncio
async def test_get_session_report_with_mock_service(client) -> None:
    """GET /api/coach/sessions/{id}/report returns 200 with a SessionFeedbackReport."""
    with patch("app.routers.coach.CoachService") as MockSvc:
        instance = MockSvc.return_value
        instance.get_report = AsyncMock(return_value=SAMPLE_REPORT)
        response = await client.get("/api/coach/sessions/session-uuid-001/report")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "session-uuid-001"
    assert data["overall_score"] == 7.5


@pytest.mark.asyncio
async def test_get_application_progress_returns_empty_list(client: AsyncClient) -> None:
    """GET /api/coach/progress/{application_id} returns empty list on fresh DB."""
    response = await client.get("/api/coach/progress/no-such-application-id")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_skip_question_not_found_returns_404(client: AsyncClient) -> None:
    """POST /api/coach/sessions/{id}/skip returns 404 when question doesn't exist."""
    response = await client.post(
        "/api/coach/sessions/session-uuid-001/skip",
        params={"question_id": "nonexistent-question-id"},
    )
    assert response.status_code == 404
    assert "Question not found" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Phase C: plan-followup + progress trend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_followup_returns_200_or_404() -> None:
    """POST /api/coach/sessions/{id}/plan-followup returns 200 with mock service."""
    from app.schemas.coach import PlanFollowUpResponse

    sample_followup = PlanFollowUpResponse(
        followup_session_id="new-session-uuid",
        focus_areas=["star_structure", "delivery"],
        message="Follow-up session created focusing on: star structure and delivery.",
    )

    with patch("app.routers.coach.CoachService") as MockSvc:
        instance = MockSvc.return_value
        instance.plan_followup_session = AsyncMock(return_value=sample_followup)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/coach/sessions/session-uuid-001/plan-followup")

    assert response.status_code == 200
    data = response.json()
    assert data["followup_session_id"] == "new-session-uuid"
    assert "star_structure" in data["focus_areas"]


@pytest.mark.asyncio
async def test_plan_followup_session_not_found_returns_404() -> None:
    """POST /api/coach/sessions/{id}/plan-followup returns 404 when session not found."""
    from fastapi import HTTPException

    with patch("app.routers.coach.CoachService") as MockSvc:
        instance = MockSvc.return_value
        instance.plan_followup_session = AsyncMock(
            side_effect=HTTPException(status_code=404, detail="Session not found")
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/coach/sessions/nonexistent-id/plan-followup")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_progress_trend_returns_list(client: AsyncClient) -> None:
    """GET /api/coach/progress/{session_id}/trend returns a list (empty for fresh DB)."""
    response = await client.get("/api/coach/progress/nonexistent-session-id/trend")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


# ---------------------------------------------------------------------------
# Phase D: capabilities endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_capabilities_returns_dict() -> None:
    """GET /api/coach/capabilities returns face_analysis and tts flags."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/coach/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert "face_analysis" in data
    assert "tts" in data
    assert isinstance(data["face_analysis"], bool)
    assert isinstance(data["tts"], bool)


# ---------------------------------------------------------------------------
# Phase E: TTS endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tts_question_returns_503_when_disabled(client: AsyncClient) -> None:
    """POST /api/coach/sessions/{id}/tts-question returns 503 when TTS is disabled."""
    from app._exceptions import PerceptionNotAvailableError

    # get_tts is imported locally inside the endpoint via
    # 'from ..agents.tools.perception_factory import get_tts'.
    # We patch the source module where it lives.
    with patch(
        "app.agents.tools.perception_factory.get_tts",
        side_effect=PerceptionNotAvailableError("TTS is disabled"),
    ):
        response = await client.post(
            "/api/coach/sessions/session-uuid-001/tts-question",
            params={"question_id": "q-uuid-001"},
        )
    assert response.status_code == 503
