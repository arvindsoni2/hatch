"""Tests for profile_loader caching and reload behaviour."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

import app.agents.tools.profile_loader as loader_module
from app.schemas.profile import Profile


@pytest.fixture(autouse=True)
def reset_loader_cache():
    """Clear the in-process cache before each test."""
    loader_module._cache = None
    loader_module._cache_mtime = 0.0
    yield
    loader_module._cache = None
    loader_module._cache_mtime = 0.0


class TestProfileLoader:

    def test_cloud_runtime_overrides_profile_llm_routes(self):
        profile = Profile()
        runtime = {
            "ai_mode": "cloud",
            "provider": "anthropic",
            "effective_routing": {"primary": "claude-sonnet-5", "triage": "claude-haiku-4-5"},
        }

        with patch("app.agents.tools.profile_loader.load_runtime", return_value=runtime):
            result = loader_module._apply_runtime_routing(profile)

        assert result.llm.provider == "anthropic"
        assert result.llm.primary_model == "claude-sonnet-5"
        assert result.llm.triage_model == "claude-haiku-4-5"
        assert result.llm.api_key_env == "ANTHROPIC_API_KEY"
        assert result.llm.base_url is None

    def test_local_runtime_never_inherits_cloud_provider(self):
        profile = Profile.model_validate({"llm": {"provider": "openai", "api_key_env": "OPENAI_API_KEY"}})
        runtime = {
            "ai_mode": "local",
            "provider": None,
            "effective_routing": {"primary": "local-primary", "triage": "local-triage"},
        }

        with patch("app.agents.tools.profile_loader.load_runtime", return_value=runtime):
            result = loader_module._apply_runtime_routing(profile)

        assert result.llm.provider == "llamacpp"
        assert result.llm.primary_model == "local-primary"
        assert result.llm.triage_model == "local-triage"
        assert result.llm.api_key_env == ""
        assert result.llm.base_url == "http://llm-primary:8080/v1"

    def test_load_returns_valid_profile(self):
        """load_profile() returns a Profile validated from profile_service."""
        mock_profile = MagicMock()

        with patch("app.agents.tools.profile_loader._load", return_value=mock_profile), \
             patch("app.agents.tools.profile_loader.get_profile_path") as mock_path:
            mock_path.return_value.exists.return_value = True
            mock_path.return_value.stat.return_value.st_mtime = 12345.0

            from app.agents.tools.profile_loader import load_profile
            result = load_profile()

        assert result is not None

    def test_load_caches_by_mtime(self):
        """Calling load_profile() twice with the same mtime reads from disk only once."""
        mock_profile = MagicMock()
        call_count = {"n": 0}

        def counting_load():
            call_count["n"] += 1
            return mock_profile

        with patch("app.agents.tools.profile_loader._load", side_effect=counting_load), \
             patch("app.agents.tools.profile_loader.get_profile_path") as mock_path:
            mock_path.return_value.exists.return_value = True
            mock_path.return_value.stat.return_value.st_mtime = 99999.0

            from app.agents.tools.profile_loader import load_profile, invalidate_cache

            invalidate_cache()
            load_profile()  # first call — reads from disk
            load_profile()  # second call — TTL not expired, should use cache

        # _load should be called exactly once
        assert call_count["n"] == 1

    def test_invalidate_cache_forces_reload(self):
        """After invalidate_cache(), the next load_profile() reads from disk."""
        mock_profile = MagicMock()
        call_count = {"n": 0}

        def counting_load():
            call_count["n"] += 1
            return mock_profile

        with patch("app.agents.tools.profile_loader._load", side_effect=counting_load), \
             patch("app.agents.tools.profile_loader.get_profile_path") as mock_path:
            mock_path.return_value.exists.return_value = True
            mock_path.return_value.stat.return_value.st_mtime = 11111.0

            from app.agents.tools.profile_loader import load_profile, invalidate_cache

            invalidate_cache()
            load_profile()   # call 1
            invalidate_cache()
            load_profile()   # call 2 — cache was invalidated

        assert call_count["n"] == 2

    def test_load_returns_profile_when_file_missing(self):
        """load_profile() returns a profile even when profile.yaml does not exist (fallback)."""
        mock_profile = MagicMock()

        with patch("app.agents.tools.profile_loader._load", return_value=mock_profile), \
             patch("app.agents.tools.profile_loader.get_profile_path") as mock_path:
            mock_path.return_value.exists.return_value = False

            from app.agents.tools.profile_loader import load_profile, invalidate_cache
            invalidate_cache()
            result = load_profile()

        assert result is not None
