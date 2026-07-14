"""Canonical setup intent normalization and patch tests."""
from __future__ import annotations

import json

import pytest

from app.schemas.setup import IntentPatch
from app.services.setup_intent import load_setup_intent, patch_setup_intent


@pytest.fixture
def tmp_config(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))
    return tmp_path


def test_legacy_ai_later_normalizes_to_explicit_none(tmp_config):
    (tmp_config / "ai_setup_intent.json").write_text(
        json.dumps({"ai_mode": "ai-later", "backend_profile": "full"})
    )

    intent = load_setup_intent()

    assert intent.ai_mode == "none"
    assert intent.backend_profile == "full"
    assert intent.schema_version == 2


def test_capability_patch_preserves_cloud_models(tmp_config):
    patch_setup_intent(IntentPatch(
        ai_mode="cloud",
        cloud_provider="openai",
        cloud_primary_model="gpt-primary",
        cloud_triage_model="gpt-triage",
    ))

    updated = patch_setup_intent(IntentPatch(backend_profile="browser"))

    assert (updated.cloud_primary_model, updated.cloud_triage_model) == (
        "gpt-primary", "gpt-triage"
    )
    assert updated.backend_profile == "browser"


def test_cloud_patch_clears_local_routing(tmp_config):
    patch_setup_intent(IntentPatch(
        ai_mode="local",
        local_primary_model="local-primary",
        local_triage_model="local-triage",
    ))

    updated = patch_setup_intent(IntentPatch(
        ai_mode="cloud",
        cloud_provider="anthropic",
        cloud_primary_model="cloud-primary",
        cloud_triage_model="cloud-triage",
    ))

    assert updated.local_primary_model is None
    assert updated.local_triage_model is None


def test_explicit_none_clears_all_model_routing_and_records_deferral(tmp_config):
    patch_setup_intent(IntentPatch(
        ai_mode="cloud",
        cloud_provider="openai",
        cloud_primary_model="primary",
        cloud_triage_model="triage",
    ))

    updated = patch_setup_intent(IntentPatch(ai_mode="none"))

    assert updated.ai_mode == "none"
    assert updated.cloud_provider is None
    assert updated.cloud_primary_model is None
    assert updated.cloud_triage_model is None
    assert updated.setup_deferred_at is not None

