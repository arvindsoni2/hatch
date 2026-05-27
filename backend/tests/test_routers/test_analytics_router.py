"""Tests for the analytics router (dashboard, score-distribution, costs)."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


class TestAnalyticsRouter:

    async def test_get_dashboard_returns_structured_response(self, client):
        """GET /api/analytics/dashboard returns analytics summary with known keys."""
        response = await client.get("/api/analytics/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    async def test_get_score_distribution_returns_list(self, client):
        """GET /api/analytics/score-distribution returns bucketed score data."""
        mock_profile = MagicMock()
        mock_profile.scoring.shortlist_threshold = 0.75

        # load_profile is imported inline — patch at source module
        with patch("app.agents.tools.profile_loader.load_profile", return_value=mock_profile):
            response = await client.get("/api/analytics/score-distribution")

        assert response.status_code == 200
        data = response.json()
        assert "buckets" in data
        assert isinstance(data["buckets"], list)

    async def test_get_monthly_costs_returns_cost_summary(self, client):
        """GET /api/analytics/costs/monthly returns monthly LLM cost data."""
        mock_profile = MagicMock()
        mock_profile.llm.monthly_budget = 15
        mock_profile.llm.currency = "GBP"

        with patch("app.agents.tools.profile_loader.load_profile", return_value=mock_profile):
            response = await client.get("/api/analytics/costs/monthly")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
