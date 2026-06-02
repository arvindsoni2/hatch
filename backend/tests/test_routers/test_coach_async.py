"""Tests that coach endpoints return 202 + job_id."""
from __future__ import annotations

import pytest


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
async def test_submit_answer_returns_202(client):
    """POST /api/coach/sessions/{id}/submit-answer returns 202 with job_id."""
    response = await client.post(
        "/api/coach/sessions/fake-session-id/submit-answer",
        params={"question_id": "fake-q-id"},
        json={"transcript": "I led a team...", "duration_ms": 45000},
    )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "submit_answer"


@pytest.mark.asyncio
async def test_end_session_returns_202(client):
    """POST /api/coach/sessions/{id}/end returns 202 with job_id."""
    response = await client.post("/api/coach/sessions/fake-session-id/end")
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "end_session"
