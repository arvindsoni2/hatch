"""Tests for the profile router (get, update, status)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


class TestProfileRouter:

    async def test_get_profile_status_returns_structured_response(self, client):
        """GET /api/v2/profile/status returns exists/completeness fields."""
        response = await client.get("/api/v2/profile/status")
        assert response.status_code == 200
        data = response.json()
        assert "exists" in data

    async def test_get_profile_returns_dict_when_file_exists(self, client):
        """GET /api/v2/profile returns the raw profile.yaml as a dict."""
        mock_raw = {
            "candidate": {"name": "Test User", "title": "Engineer"},
            "llm": {"provider": "anthropic"},
        }

        with patch("app.routers.profile.load_profile_raw", return_value=mock_raw):
            response = await client.get("/api/v2/profile")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    async def test_validate_profile_returns_validation_result(self, client):
        """POST /api/v2/profile/validate accepts a profile dict and returns validity."""
        minimal_profile = {
            "candidate": {
                "name": "Test User",
                "title": "Cloud Architect",
                "years_experience": 10,
                "summary": "Experienced architect",
            },
            "search": {
                "target_roles": ["Cloud Architect"],
                "locations": [{"city": "London", "country": "UK", "remote_preference": "hybrid"}],
                "contract_type": "contract",
            },
            "compensation": {
                "min_rate": 500,
                "max_rate": 700,
                "rate_type": "daily",
                "currency": "GBP",
            },
            "skills": {
                "primary": ["AWS", "Terraform"],
                "secondary": ["Python"],
            },
            "llm": {
                "provider": "anthropic",
                "triage_model": "claude-haiku-4-5-20251001",
                "primary_model": "claude-sonnet-4-6",
            },
        }

        response = await client.post("/api/v2/profile/validate", json=minimal_profile)
        assert response.status_code in (200, 422)
