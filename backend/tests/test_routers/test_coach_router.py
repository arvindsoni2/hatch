"""Integration tests for /api/coach router — create session, submit answer, end session, 404 handling."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
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
async def test_submit_answer_returns_202(client) -> None:
    """POST /api/coach/sessions/{id}/submit-answer returns 202 with job_id (async pattern)."""
    response = await client.post(
        "/api/coach/sessions/session-uuid-001/submit-answer",
        params={"question_id": "q-uuid-001"},
        json={"transcript": "In my previous role at a FTSE 100 company...", "duration_ms": 60000},
    )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "submit_answer"


@pytest.mark.asyncio
async def test_end_session_returns_202(client) -> None:
    """POST /api/coach/sessions/{id}/end returns 202 with job_id (async pattern)."""
    response = await client.post("/api/coach/sessions/session-uuid-001/end")
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "end_session"


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
async def test_get_session_report_with_mock_service() -> None:
    """GET /api/coach/sessions/{id}/report returns 200 with a SessionFeedbackReport."""
    with patch("app.routers.coach.CoachService") as MockSvc:
        instance = MockSvc.return_value
        instance.get_report = AsyncMock(return_value=SAMPLE_REPORT)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
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
