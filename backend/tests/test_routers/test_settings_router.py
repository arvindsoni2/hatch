"""Tests for the settings router (API key management)."""
from __future__ import annotations

from unittest.mock import patch, MagicMock, AsyncMock


class TestSettingsRouter:

    async def test_get_env_status_returns_configured_providers(self, client):
        """GET /api/v2/settings/env/status returns structured provider info."""
        mock_profile = MagicMock()
        mock_profile.llm.provider = "anthropic"

        # load_profile is imported inline inside get_env_status — patch at source
        with patch("app.services.profile_service.load_profile", return_value=mock_profile):
            response = await client.get("/api/v2/settings/env/status")

        assert response.status_code == 200
        data = response.json()
        assert "configured_providers" in data
        assert "current_provider" in data
        # Ollama is always listed as it requires no key
        assert "ollama" in data["configured_providers"]

    async def test_put_env_validates_key_before_saving(self, client):
        """PUT /api/v2/settings/env returns 400 for an unknown key_name."""
        response = await client.put(
            "/api/v2/settings/env",
            json={"key_name": "UNKNOWN_KEY", "key_value": "some-value"},
        )
        assert response.status_code == 400

    async def test_put_env_does_not_return_key_value_in_response(self, client):
        """PUT /api/v2/settings/env must never return the actual key value."""
        mock_llm = AsyncMock()
        build_model = MagicMock(return_value=mock_llm)
        mock_profile = MagicMock()
        mock_profile.llm.provider = "anthropic"
        mock_profile.llm.triage_model = "claude-haiku-4-5-20251001"
        mock_profile.llm.api_key_env = "ANTHROPIC_API_KEY"

        # _build_model and load_profile are imported inline — patch at their source modules
        # Also patch _write_env_key to avoid filesystem writes (data/ may be owned by container)
        with patch("app.agents.tools.llm_factory._build_model", build_model), \
             patch("app.services.profile_service.load_profile", return_value=mock_profile), \
             patch("app.routers.settings.load_profile_raw", return_value={"llm": {}}), \
             patch("app.routers.settings.save_profile_raw"), \
             patch("app.routers.settings.invalidate_cache"), \
             patch("app.routers.settings._write_env_key"):
            response = await client.put(
                "/api/v2/settings/env",
                json={"key_name": "ANTHROPIC_API_KEY", "key_value": "sk-ant-test123"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "sk-ant-test123" not in str(data)
        assert "key_value" not in data
        test_cfg = build_model.call_args.args[1]
        assert test_cfg.base_url is None
        assert test_cfg.triage_base_url == ""


def test_write_env_key_sets_file_mode_600(tmp_path, monkeypatch):
    """_write_env_key must chmod the file to 0600 after writing (SEC-8)."""
    import stat
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    # Re-import to pick up the patched DATA_DIR
    import importlib
    import sys
    for mod in list(sys.modules.keys()):
        if "app.routers.settings" in mod:
            del sys.modules[mod]
    import app.routers.settings as settings_mod
    import importlib
    importlib.reload(settings_mod)

    settings_mod._write_env_key("ANTHROPIC_API_KEY", "sk-test")
    written_file = tmp_path / "api_keys.env"
    assert written_file.exists()
    mode = stat.S_IMODE(written_file.stat().st_mode)
    assert mode == 0o600, f"Expected 0600, got {oct(mode)}"
