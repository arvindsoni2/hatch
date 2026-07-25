"""Tests for master profile loader — SEC-4 example-file fallback."""
from __future__ import annotations

from unittest.mock import patch


def test_load_master_profile_falls_back_to_example(tmp_path):
    """load_master_profile() uses the example YAML when master_profile.yaml is absent."""
    import app.config as cfg_pkg

    # Override the paths to point to tmp_path (no real profile present)
    example_content = """
candidate:
  name: "Your Name"
  location: "Your City"
rate:
  min_daily: 400
  max_daily: 600
  currency: GBP
"""
    example_path = tmp_path / "master_profile.example.yaml"
    example_path.write_text(example_content)

    with patch.object(cfg_pkg, "_PROFILE_PATH", tmp_path / "master_profile.yaml"), \
         patch.object(cfg_pkg, "_PROFILE_EXAMPLE_PATH", example_path):
        # Clear the lru_cache so our patched paths are used
        cfg_pkg.load_master_profile.cache_clear()
        result = cfg_pkg.load_master_profile()
        cfg_pkg.load_master_profile.cache_clear()  # restore clean state

    assert result["candidate"]["name"] == "Your Name"


def test_load_master_profile_prefers_real_file(tmp_path):
    """load_master_profile() loads the real profile when it exists."""
    import app.config as cfg_pkg

    real_content = """
candidate:
  name: "Real User"
  location: "Real City"
"""
    real_path = tmp_path / "master_profile.yaml"
    real_path.write_text(real_content)
    example_path = tmp_path / "master_profile.example.yaml"
    example_path.write_text("candidate:\n  name: 'Template'\n")

    with patch.object(cfg_pkg, "_PROFILE_PATH", real_path), \
         patch.object(cfg_pkg, "_PROFILE_EXAMPLE_PATH", example_path):
        cfg_pkg.load_master_profile.cache_clear()
        result = cfg_pkg.load_master_profile()
        cfg_pkg.load_master_profile.cache_clear()

    assert result["candidate"]["name"] == "Real User"
