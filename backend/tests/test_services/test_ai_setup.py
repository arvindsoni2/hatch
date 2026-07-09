from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import ai_setup


def test_catalogue_is_pinned_and_valid() -> None:
    catalogue = ai_setup.load_catalog()

    assert len(catalogue) == 2
    assert {model["role"] for model in catalogue} == {
        "triage",
        "combined_capable_primary",
    }
    assert all(len(model["source_revision"]) == 40 for model in catalogue)
    assert all(len(model["sha256"]) == 64 for model in catalogue)
    assert all(model["format"] == "gguf" for model in catalogue)


def test_recommendations_use_total_ram_and_are_exclusive(tmp_path: Path) -> None:
    result = ai_setup.recommend_models(
        os_family="linux",
        arch="x86_64",
        total_ram_gb=12,
        free_disk_gb=20,
        models_dir=tmp_path,
    )

    recommended = {item["model_id"] for item in result["recommended"]}
    compatible = {item["model_id"] for item in result["compatible"]}
    rejected = {item["model_id"] for item in result["not_recommended"]}

    assert "qwen3.5-0.8b-q8-triage" in recommended
    assert "qwen3.5-4b-q4km-primary" in recommended
    assert not (recommended & compatible or recommended & rejected or compatible & rejected)


def test_recommendations_reject_unsupported_platform(tmp_path: Path) -> None:
    result = ai_setup.recommend_models(
        os_family="unknown",
        arch="riscv64",
        total_ram_gb=64,
        free_disk_gb=100,
        models_dir=tmp_path,
    )

    assert len(result["not_recommended"]) == 2
    assert all(len(item["reasons"]) == 2 for item in result["not_recommended"])


def test_intent_write_is_non_secret_and_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))
    payload = ai_setup.AISetupIntent(
        ai_mode="cloud",
        provider="openai",
        provider_metadata={"model": "example"},
        restart_required=True,
    )

    saved = ai_setup.save_intent(payload)

    assert saved["provider"] == "openai"
    assert json.loads((tmp_path / "ai_setup_intent.json").read_text()) == saved
    assert (tmp_path / "ai_setup_intent.json").stat().st_mode & 0o777 == 0o600


def test_provider_aliases_canonicalize_to_stored_ids() -> None:
    assert ai_setup.canonical_provider("google_gemini") == "google_genai"
    assert ai_setup.canonical_provider("google") == "google_genai"
    assert ai_setup.canonical_provider("openrouter") == "openrouter"


def test_provider_secret_env_includes_openrouter() -> None:
    assert ai_setup.provider_secret_env("openrouter") == "OPENROUTER_API_KEY"
    assert ai_setup.provider_secret_env("google_gemini") == "GOOGLE_API_KEY"


def test_easy_install_defaults_to_not_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))

    runtime = ai_setup.load_runtime()

    assert runtime["ai_mode"] == "not_configured"
    assert runtime["feature_gates"]["cv_tailoring"] is False
