"""Derived setup readiness and ordered host-action tests."""
from __future__ import annotations

import json

import pytest

from app.schemas.setup import IntentPatch
from app.services.setup_intent import patch_setup_intent
from app.services.setup_status import build_setup_status


def _write(path, name: str, value: dict) -> None:
    (path / name).write_text(json.dumps(value), encoding="utf-8")


@pytest.mark.asyncio
async def test_local_selection_without_models_is_pending_not_ready(
    db_session,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("HATCH_PROBE_DIR", str(tmp_path))
    patch_setup_intent(IntentPatch(
        ai_mode="local",
        local_primary_model="qwen3.5-4b-q4km-primary",
        local_triage_model="qwen3.5-0.8b-q8-triage",
    ))
    _write(tmp_path, "hardware_probe_latest.json", {
        "sanitised": True,
        "memory": {"total_gb": 16},
        "storage": {"models_dir_free_gb": 30},
        "platform": {"os_family": "linux", "arch": "x86_64"},
    })

    status = await build_setup_status(db_session)

    assert status["overall_status"] == "pending_host_action"
    assert [action["id"] for action in status["next_actions"]][:2] == [
        "models.install", "ai.apply"
    ]


@pytest.mark.asyncio
async def test_cloud_ready_never_requires_local_overlay(
    db_session,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))
    patch_setup_intent(IntentPatch(
        ai_mode="cloud",
        cloud_provider="openai",
        cloud_primary_model="gpt-5.6",
        cloud_triage_model="gpt-5.6",
    ))
    _write(tmp_path, "ai_runtime.json", {
        "ai_mode": "cloud",
        "provider": "openai",
        "effective_routing": {"primary": "gpt-5.6", "triage": "gpt-5.6"},
    })
    monkeypatch.setattr(
        "app.services.setup_status.provider_validation_status",
        lambda *_args: {"status": "ready", "validated_at": "2026-07-14T12:00:00Z"},
    )

    status = await build_setup_status(db_session)

    assert status["overall_status"] == "ready"
    assert status["local_ai"]["status"] == "not_selected"
    assert all(not action["id"].startswith("models.") for action in status["next_actions"])


@pytest.mark.asyncio
async def test_status_exposes_authoritative_onboarding_state(db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))
    patch_setup_intent(IntentPatch(ai_mode="none"))

    status = await build_setup_status(db_session)

    assert status["onboarding"] == {
        "status": "not_started",
        "last_completed_step": None,
    }
    assert status["onboarding_complete"] is False
