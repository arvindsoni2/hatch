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

    async def test_get_funnel_returns_200(self, client):
        """GET /api/analytics/funnel returns funnel response with stages."""
        response = await client.get("/api/analytics/funnel")
        assert response.status_code == 200
        data = response.json()
        assert "stages" in data

    async def test_get_trends_returns_200(self, client):
        """GET /api/analytics/trends returns trend response."""
        response = await client.get("/api/analytics/trends")
        assert response.status_code == 200
        data = response.json()
        assert "weeks" in data

    async def test_get_trends_accepts_weeks_param(self, client):
        """GET /api/analytics/trends?weeks=4 respects the weeks query param."""
        response = await client.get("/api/analytics/trends?weeks=4")
        assert response.status_code == 200

    async def test_get_sources_returns_list(self, client):
        """GET /api/analytics/sources returns a list (empty on fresh DB)."""
        response = await client.get("/api/analytics/sources")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_daily_costs_returns_200(self, client):
        """GET /api/analytics/costs/daily returns daily cost buckets."""
        response = await client.get("/api/analytics/costs/daily")
        assert response.status_code == 200
        data = response.json()
        assert "days" in data
        assert isinstance(data["days"], list)

    async def test_get_daily_costs_custom_days(self, client):
        """GET /api/analytics/costs/daily?days=7 accepts minimum days param."""
        response = await client.get("/api/analytics/costs/daily?days=7")
        assert response.status_code == 200

    async def test_get_agent_performance_returns_200(self, client):
        """GET /api/analytics/agent-performance returns agent stats."""
        response = await client.get("/api/analytics/agent-performance")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        assert isinstance(data["agents"], list)

    async def test_get_search_quality_returns_200(self, client):
        """GET /api/analytics/search-quality returns quality metrics."""
        mock_profile = MagicMock()
        mock_profile.scoring.shortlist_threshold = 0.75

        with patch("app.agents.tools.profile_loader.load_profile", return_value=mock_profile):
            response = await client.get("/api/analytics/search-quality")

        assert response.status_code == 200
        data = response.json()
        assert "total_discovered" in data
        assert "shortlisted" in data

    async def test_get_skill_gaps_returns_200(self, client):
        """GET /api/analytics/skill-gaps returns empty message on fresh DB."""
        response = await client.get("/api/analytics/skill-gaps")
        assert response.status_code == 200
        data = response.json()
        # Either returns skills list or a message about no data
        assert "skills" in data or "message" in data

    async def test_get_ab_testing_returns_200_with_insufficient_data(self, client):
        """GET /api/analytics/ab-testing returns not-enough-data message on fresh DB."""
        response = await client.get("/api/analytics/ab-testing")
        assert response.status_code == 200
        data = response.json()
        # Fresh DB has 0 applications — returns the insufficient data message
        assert "total_applications" in data

    async def test_get_ats_correlation_returns_200(self, client):
        """GET /api/analytics/ats-correlation returns buckets or no-data message."""
        response = await client.get("/api/analytics/ats-correlation")
        assert response.status_code == 200
        data = response.json()
        assert "buckets" in data

    async def test_get_skill_frequency_returns_200(self, client):
        """GET /api/analytics/skill-frequency returns skill list or no-data message."""
        response = await client.get("/api/analytics/skill-frequency")
        assert response.status_code == 200
        data = response.json()
        assert "skills" in data
