"""Tests for the profile router (get, update, status)."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from unittest.mock import patch


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

    @pytest.mark.asyncio
    async def test_test_connection_rejects_browser_owned_secret(self, client) -> None:
        """Legacy profile route must preserve the host-owned secret boundary."""
        import os

        sentinel = os.environ.get("ANTHROPIC_API_KEY", "ORIGINAL_SENTINEL")

        resp = await client.post(
            "/api/v2/profile/test-connection",
            json={"provider": "anthropic", "api_key": "sk-test-key-12345"},
        )

        assert resp.status_code == 422
        assert "host CLI" in resp.json()["detail"]
        assert "sk-test-key-12345" not in resp.text
        assert os.environ.get("ANTHROPIC_API_KEY", "ORIGINAL_SENTINEL") == sentinel

    @pytest.mark.asyncio
    async def test_llamacpp_connection_checks_bundled_services(self, client) -> None:
        """The onboarding check must probe llama.cpp, not default to Anthropic."""
        with patch(
            "app.routers.profile._test_llamacpp_services",
            return_value={"ok": True},
        ) as probe:
            resp = await client.post(
                "/api/v2/profile/test-connection",
                json={"provider": "llamacpp", "api_key": ""},
            )

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        probe.assert_awaited_once()


@pytest.mark.asyncio
async def test_security_headers_present_on_every_response(client: AsyncClient) -> None:
    """Every API response must include X-Content-Type-Options, X-Frame-Options, Referrer-Policy."""
    resp = await client.get("/api/health")
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
