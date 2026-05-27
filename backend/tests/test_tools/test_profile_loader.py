"""Tests for profile_loader caching and reload behaviour."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

import app.agents.tools.profile_loader as loader_module


@pytest.fixture(autouse=True)
def reset_loader_cache():
    """Clear the in-process cache before each test."""
    loader_module._cache = None
    loader_module._cache_mtime = 0.0
    yield
    loader_module._cache = None
    loader_module._cache_mtime = 0.0


class TestProfileLoader:

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
