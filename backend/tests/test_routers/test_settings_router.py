"""Tests for the settings router (API key management)."""
from __future__ import annotations

from unittest.mock import patch, MagicMock


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

    async def test_put_env_rejects_browser_secret_writes(self, client):
        """PUT /api/v2/settings/env directs all secret writes to the host CLI."""
        response = await client.put(
            "/api/v2/settings/env",
            json={"key_name": "UNKNOWN_KEY", "key_value": "some-value"},
        )
        assert response.status_code == 410
        assert "hatch secrets set" in response.json()["detail"]

    async def test_put_env_never_echoes_key_value(self, client):
        response = await client.put(
            "/api/v2/settings/env",
            json={"key_name": "ANTHROPIC_API_KEY", "key_value": "sk-ant-test123"},
        )

        assert response.status_code == 410
        data = response.json()
        assert "sk-ant-test123" not in str(data)
        assert "key_value" not in data


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
    importlib.reload(settings_mod)

    settings_mod._write_env_key("ANTHROPIC_API_KEY", "sk-test")
    written_file = tmp_path / "api_keys.env"
    assert written_file.exists()
    mode = stat.S_IMODE(written_file.stat().st_mode)
    assert mode == 0o600, f"Expected 0600, got {oct(mode)}"
