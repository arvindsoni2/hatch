from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest


OPTIONAL_ENV = (
    "HATCH_BACKEND_PROFILE",
    "HATCH_BROWSER_AUTOMATION_ENABLED",
    "HATCH_LOCAL_EMBEDDINGS_ENABLED",
    "HATCH_PERCEPTION_ENABLED",
    "HATCH_ADVANCED_COACH_ENABLED",
)


def _clear_capability_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in OPTIONAL_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.asyncio
async def test_system_capabilities_defaults_to_core(client, monkeypatch: pytest.MonkeyPatch):
    _clear_capability_env(monkeypatch)
    monkeypatch.setenv("HATCH_CONFIG_DIR", "/tmp/hatch-test-config")

    response = await client.get("/api/system/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert body["backend_profile"] == "core"
    assert body["ai_mode"] == "not_configured"
    assert body["capabilities"]["core_backend"] == {
        "configured": True,
        "installed": True,
        "available": True,
        "reason": None,
        "enable_command": None,
    }
    assert body["capabilities"]["browser_automation"]["configured"] is False
    assert body["capabilities"]["browser_automation"]["available"] is False
    assert body["capabilities"]["browser_automation"]["enable_command"] == "hatch capabilities enable browser"
    assert body["capabilities"]["local_embeddings"]["enable_command"] == "hatch capabilities enable local-embeddings"
    assert body["capabilities"]["perception_advanced_coach"]["enable_command"] == "hatch capabilities enable full"


@pytest.mark.asyncio
async def test_system_capabilities_reports_browser_profile_configured(client, monkeypatch: pytest.MonkeyPatch):
    _clear_capability_env(monkeypatch)
    monkeypatch.setenv("HATCH_BACKEND_PROFILE", "browser")
    monkeypatch.setenv("HATCH_BROWSER_AUTOMATION_ENABLED", "1")

    import app.services.backend_capabilities as backend_capabilities

    monkeypatch.setattr(
        backend_capabilities.importlib.util,
        "find_spec",
        lambda module_name: SimpleNamespace(name=module_name) if module_name == "playwright" else None,
    )

    response = await client.get("/api/system/capabilities")

    assert response.status_code == 200
    browser = response.json()["capabilities"]["browser_automation"]
    assert browser["configured"] is True
    assert browser["installed"] is True
    assert browser["available"] is True
    assert browser["reason"] is None


@pytest.mark.asyncio
async def test_system_capabilities_reports_local_embeddings_configured(client, monkeypatch: pytest.MonkeyPatch):
    _clear_capability_env(monkeypatch)
    monkeypatch.setenv("HATCH_BACKEND_PROFILE", "local-embeddings")
    monkeypatch.setenv("HATCH_LOCAL_EMBEDDINGS_ENABLED", "1")

    import app.services.backend_capabilities as backend_capabilities

    monkeypatch.setattr(
        backend_capabilities.importlib.util,
        "find_spec",
        lambda module_name: SimpleNamespace(name=module_name) if module_name == "sentence_transformers" else None,
    )

    response = await client.get("/api/system/capabilities")

    assert response.status_code == 200
    local_embeddings = response.json()["capabilities"]["local_embeddings"]
    assert local_embeddings["configured"] is True
    assert local_embeddings["installed"] is True
    assert local_embeddings["available"] is True


@pytest.mark.asyncio
async def test_system_capabilities_full_profile_configures_all_optional_groups(client, monkeypatch: pytest.MonkeyPatch):
    _clear_capability_env(monkeypatch)
    monkeypatch.setenv("HATCH_BACKEND_PROFILE", "full")
    monkeypatch.setenv("HATCH_BROWSER_AUTOMATION_ENABLED", "1")
    monkeypatch.setenv("HATCH_LOCAL_EMBEDDINGS_ENABLED", "1")
    monkeypatch.setenv("HATCH_PERCEPTION_ENABLED", "1")
    monkeypatch.setenv("HATCH_ADVANCED_COACH_ENABLED", "1")

    import app.services.backend_capabilities as backend_capabilities

    monkeypatch.setattr(backend_capabilities.importlib.util, "find_spec", lambda _module_name: None)

    response = await client.get("/api/system/capabilities")

    assert response.status_code == 200
    capabilities = response.json()["capabilities"]
    for key in ("browser_automation", "local_embeddings", "perception_advanced_coach"):
        assert capabilities[key]["configured"] is True
        assert capabilities[key]["installed"] is False
        assert capabilities[key]["available"] is False
        assert "not installed" in capabilities[key]["reason"].lower()


def test_backend_capability_checks_do_not_import_optional_packages(monkeypatch: pytest.MonkeyPatch):
    _clear_capability_env(monkeypatch)
    monkeypatch.setenv("HATCH_BACKEND_PROFILE", "full")

    for module_name in ("playwright", "sentence_transformers", "transformers", "faster_whisper"):
        sys.modules.pop(module_name, None)

    import app.services.backend_capabilities as backend_capabilities

    checked: list[str] = []

    def fake_find_spec(module_name: str):
        checked.append(module_name)
        return None

    monkeypatch.setattr(backend_capabilities.importlib.util, "find_spec", fake_find_spec)

    backend_capabilities.build_backend_capability_status()

    assert checked == ["playwright", "sentence_transformers", "faster_whisper"]
    for module_name in ("playwright", "sentence_transformers", "transformers", "faster_whisper"):
        assert module_name not in sys.modules
