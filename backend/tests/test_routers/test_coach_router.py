"""Integration tests for /api/coach router — create session, submit answer, end session, 404 handling."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.schemas.coach import (
    AnswerEvaluation,
    CompanyResearchResponse,
    QuestionPresentation,
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
async def test_create_session_returns_201() -> None:
    """POST /api/coach/sessions creates a session and returns 201."""
    with patch("app.routers.coach.CoachService") as MockSvc:
        instance = MockSvc.return_value
        instance.create_session = AsyncMock(return_value=SAMPLE_SESSION_RESPONSE)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/coach/sessions",
                json={
                    "company_name": "Accenture",
                    "role_title": "Solutions Architect",
                    "config": {"question_count": 5},
                },
            )
    assert response.status_code == 201
    data = response.json()
    assert data["company_name"] == "Accenture"
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_submit_answer_returns_200() -> None:
    """POST /api/coach/sessions/{id}/submit-answer returns 200 with AnswerEvaluation."""
    with patch("app.routers.coach.CoachService") as MockSvc:
        instance = MockSvc.return_value
        instance.submit_answer = AsyncMock(return_value=SAMPLE_EVALUATION)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/coach/sessions/session-uuid-001/submit-answer",
                params={"question_id": "q-uuid-001"},
                json={"transcript": "In my previous role at a FTSE 100 company...", "duration_ms": 60000},
            )
    assert response.status_code == 200
    data = response.json()
    assert "overall" in data
    assert data["overall"] == 7.5


@pytest.mark.asyncio
async def test_end_session_returns_200() -> None:
    """POST /api/coach/sessions/{id}/end returns 200 with SessionFeedbackReport."""
    with patch("app.routers.coach.CoachService") as MockSvc:
        instance = MockSvc.return_value
        instance.end_session = AsyncMock(return_value=SAMPLE_REPORT)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/coach/sessions/session-uuid-001/end")
    assert response.status_code == 200
    data = response.json()
    assert data["overall_score"] == 7.5
    assert "executive_summary" in data


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
