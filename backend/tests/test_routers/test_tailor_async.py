"""Tests that tailor endpoints return 202 + job_id instead of blocking."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _mock_master_cv_present(tmp_path):
    """Pretend a master CV file exists so pre-flight check doesn't return 409."""
    fake_path = tmp_path / "master_cv.json"
    fake_path.write_text("{}")
    mock_path = MagicMock()
    mock_path.exists.return_value = True
    with patch("app.routers.tailor.resolve_master_cv_path", return_value=mock_path):
        yield


@pytest.mark.asyncio
async def test_analyse_jd_text_returns_202(client):
    """POST /api/tailor/analyse returns 202 with job_id immediately."""
    response = await client.post(
        "/api/tailor/analyse",
        params={"job_description": "Senior Python developer role"},
    )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "pending"
    assert data["type"] == "tailor_analyse"


@pytest.mark.asyncio
async def test_generate_cv_returns_202(client):
    """POST /api/tailor/generate-cv returns 202 with job_id."""
    response = await client.post(
        "/api/tailor/generate-cv",
        json={"application_id": "test-app-id", "variant": "A", "jd_text": "Senior Python dev"},
    )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "tailor_generate_cv"


@pytest.mark.asyncio
async def test_generate_cl_returns_202(client):
    """POST /api/tailor/generate-cl returns 202 with job_id."""
    response = await client.post(
        "/api/tailor/generate-cl",
        json={"application_id": "test-app-id", "variant": "A", "jd_text": "Senior Python dev"},
    )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "tailor_generate_cl"


@pytest.mark.asyncio
async def test_generate_all_returns_202(client):
    """POST /api/tailor/generate returns 202 with job_id."""
    response = await client.post(
        "/api/tailor/generate",
        json={"application_id": "test-app-id", "variant": "A", "jd_text": "Senior Python dev"},
    )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "tailor_generate"
