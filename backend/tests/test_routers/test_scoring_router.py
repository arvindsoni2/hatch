"""Integration tests for /api/v2/scoring router — insights endpoint."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_scoring_insights_returns_200(client: AsyncClient) -> None:
    """GET /api/v2/scoring/insights returns 200."""
    resp = await client.get("/api/v2/scoring/insights")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_scoring_insights_response_is_dict(client: AsyncClient) -> None:
    """GET /api/v2/scoring/insights response is a JSON object."""
    resp = await client.get("/api/v2/scoring/insights")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)
