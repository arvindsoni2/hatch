from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("hatch_cli", ROOT / "scripts" / "hatch_cli.py")
assert SPEC and SPEC.loader
hatch_cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hatch_cli)


def configure_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hatch_cli, "HATCH_HOME", tmp_path)
    monkeypatch.setattr(hatch_cli, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(hatch_cli, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr(hatch_cli, "PROBE_DIR", tmp_path / "probe")
    monkeypatch.setattr(hatch_cli, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(hatch_cli, "BACKUPS_DIR", tmp_path / "backups")
    monkeypatch.setattr(hatch_cli, "RUNTIME_PATH", tmp_path / "config" / "ai_runtime.json")
    monkeypatch.setattr(hatch_cli, "INTENT_PATH", tmp_path / "config" / "ai_setup_intent.json")
    monkeypatch.setattr(hatch_cli, "SECRETS_PATH", tmp_path / "config" / "secrets.env")


def test_secret_file_is_restrictive_and_never_accepts_newlines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_home(tmp_path, monkeypatch)
    hatch_cli.ensure_home()

    hatch_cli.write_env({"OPENAI_API_KEY": "test-value"})

    assert hatch_cli.read_env(hatch_cli.SECRETS_PATH) == {"OPENAI_API_KEY": "test-value"}
    assert hatch_cli.SECRETS_PATH.stat().st_mode & 0o777 == 0o600
    with pytest.raises(SystemExit):
        hatch_cli.write_env({"OPENAI_API_KEY": "bad\nvalue"})


def test_triage_only_runtime_disables_quality_features(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_home(tmp_path, monkeypatch)
    hatch_cli.ensure_home()
    model = next(item for item in hatch_cli.catalog() if item["role"] == "triage")
    (hatch_cli.MODELS_DIR / model["filename"]).write_bytes(b"present")

    runtime = hatch_cli.runtime_for_local([model["id"]])

    assert runtime["quality_mode"] == "triage_only"
    assert not any(runtime["feature_gates"].values())


def test_uninstall_without_purge_preserves_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_home(tmp_path, monkeypatch)
    hatch_cli.ensure_home()
    marker = tmp_path / "config" / "marker"
    marker.write_text("keep")
    monkeypatch.setattr(hatch_cli, "run", lambda *args, **kwargs: None)
    args = type("Args", (), {
        "purge_config": False, "purge_models": False, "purge_secrets": False,
        "purge_data": False, "purge_all": False, "yes": False,
    })()

    hatch_cli.cmd_uninstall(args)

    assert marker.read_text() == "keep"
