"""Tests that emails/generate and ghost/analyse return 202."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_generate_email_returns_202(client):
    """POST /api/emails/generate/{id} returns 202 with job_id."""
    response = await client.post(
        "/api/emails/generate/fake-app-id",
        json={"email_type": "post_application"},
    )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "email_generate"


@pytest.mark.asyncio
async def test_analyse_ghost_returns_202(client):
    """POST /api/ghost/analyse/{job_id} returns 202 with job_id."""
    response = await client.post("/api/ghost/analyse/fake-job-id")
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "ghost_analyse"
