"""G-1 tests — master CV path resolution and store behaviour."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.master_cv_store import (
    MasterCVMissingError,
    invalidate_cache,
    load_master_cv,
    resolve_master_cv_path,
)

_PROFILE_LOADER_TARGET = "app.agents.tools.profile_loader.load_profile"


def _make_mock_profile(path: str):
    p = MagicMock()
    p.master_cv_path = path
    return p


# ---------------------------------------------------------------------------
# resolve_master_cv_path
# ---------------------------------------------------------------------------


class TestResolveMasterCVPath:
    def test_uses_profile_master_cv_path(self, tmp_path):
        """Absolute path from profile is returned as-is."""
        expected = tmp_path / "my_cv.json"
        mock_profile = _make_mock_profile(str(expected))
        with patch(_PROFILE_LOADER_TARGET, return_value=mock_profile):
            result = resolve_master_cv_path()
        assert result == expected

    def test_env_data_dir_overrides_relative_path(self, tmp_path, monkeypatch):
        """DATA_DIR env var redirects relative paths to that directory."""
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        mock_profile = _make_mock_profile("./data/master_cv.json")
        with patch(_PROFILE_LOADER_TARGET, return_value=mock_profile):
            result = resolve_master_cv_path()
        assert result.parent == tmp_path
        assert result.name == "master_cv.json"

    def test_fallback_when_profile_load_fails(self, monkeypatch):
        """Falls back to default ./data/master_cv.json when profile load raises."""
        monkeypatch.delenv("DATA_DIR", raising=False)
        with patch(_PROFILE_LOADER_TARGET, side_effect=Exception("no profile")):
            result = resolve_master_cv_path()
        assert result.name == "master_cv.json"


# ---------------------------------------------------------------------------
# load_master_cv
# ---------------------------------------------------------------------------


class TestLoadMasterCV:
    def setup_method(self):
        invalidate_cache()

    def test_raises_missing_error_when_file_absent(self, tmp_path):
        """MasterCVMissingError raised with Settings→Resume hint when file absent."""
        mock_profile = _make_mock_profile(str(tmp_path / "no_file.json"))
        with patch(_PROFILE_LOADER_TARGET, return_value=mock_profile):
            with pytest.raises(MasterCVMissingError, match="Settings → Resume"):
                load_master_cv()

    def test_loads_and_returns_content(self, tmp_path):
        """Returns the parsed JSON content from the correct path."""
        cv_file = tmp_path / "master_cv.json"
        data = {"personal": {"full_name": "Jane Smith"}, "experience": []}
        cv_file.write_text(json.dumps(data))
        mock_profile = _make_mock_profile(str(cv_file))
        with patch(_PROFILE_LOADER_TARGET, return_value=mock_profile):
            result = load_master_cv()
        assert result["personal"]["full_name"] == "Jane Smith"

    def test_does_not_read_templates_path(self):
        """Regression tripwire: templates/master_cv.json must be deleted."""
        template_path = (
            Path(__file__).parent.parent.parent / "app" / "templates" / "master_cv.json"
        )
        assert not template_path.exists(), (
            "templates/master_cv.json still exists — G-1 requires it to be deleted"
        )

    def test_cache_invalidates_on_mtime_change(self, tmp_path):
        """Re-reads the file when mtime changes (re-upload scenario)."""
        cv_file = tmp_path / "master_cv.json"
        cv_file.write_text(json.dumps({"personal": {"full_name": "First Version"}}))
        mock_profile = _make_mock_profile(str(cv_file))

        with patch(_PROFILE_LOADER_TARGET, return_value=mock_profile):
            result1 = load_master_cv()
            assert result1["personal"]["full_name"] == "First Version"

            # Simulate re-upload: write new content and advance mtime
            cv_file.write_text(json.dumps({"personal": {"full_name": "Updated CV"}}))
            os.utime(cv_file, (time.time() + 1, time.time() + 1))

            result2 = load_master_cv()
        assert result2["personal"]["full_name"] == "Updated CV"

    def test_cv_tailor_reads_profile_path_not_template(self, tmp_path):
        """CVTailor._load_master_cv() uses the store, not the old hardcoded path."""
        from app.services.cv_tailor import CVTailor

        cv_file = tmp_path / "master_cv.json"
        cv_file.write_text(json.dumps({"personal": {"full_name": "Profile User"}}))
        mock_profile = _make_mock_profile(str(cv_file))
        invalidate_cache()

        with patch(_PROFILE_LOADER_TARGET, return_value=mock_profile):
            tailor = CVTailor(AsyncMock())
            result = tailor._load_master_cv()

        assert result["personal"]["full_name"] == "Profile User"
