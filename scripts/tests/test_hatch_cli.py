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
    monkeypatch.setattr(hatch_cli, "INSTALL_PATH", tmp_path / "config" / "install.json")
    monkeypatch.setattr(
        hatch_cli,
        "BACKEND_CAPABILITIES_PATH",
        tmp_path / "config" / "backend_capabilities.json",
        raising=False,
    )


def _compose_file_names(args: list[str]) -> list[str]:
    return [Path(args[index + 1]).name for index, value in enumerate(args) if value == "-f"]


def _compose_profiles(args: list[str]) -> list[str]:
    return [
        args[index + 1]
        for index, value in enumerate(args)
        if value == "--profile"
    ]


def test_backend_capabilities_missing_config_defaults_to_core(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_home(tmp_path, monkeypatch)

    config = hatch_cli.read_backend_capabilities()

    assert config["profile"] == "core"
    assert config["enabled"] == []


def test_backend_capabilities_invalid_json_falls_back_to_core(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_home(tmp_path, monkeypatch)
    hatch_cli.ensure_home()
    hatch_cli.BACKEND_CAPABILITIES_PATH.write_text("{not-json", encoding="utf-8")

    config = hatch_cli.read_backend_capabilities()

    assert config["profile"] == "core"
    assert "Invalid backend capability config" in capsys.readouterr().err


def test_backend_capabilities_write_uses_canonical_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_home(tmp_path, monkeypatch)
    hatch_cli.ensure_home()

    hatch_cli.write_backend_capabilities("local-embeddings", updated_by="test")

    payload = json.loads(hatch_cli.BACKEND_CAPABILITIES_PATH.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["profile"] == "local-embeddings"
    assert payload["enabled"] == ["local-embeddings"]
    assert payload["updated_by"] == "test"
    assert hatch_cli.BACKEND_CAPABILITIES_PATH.stat().st_mode & 0o777 == 0o600


def test_enabled_capabilities_are_derived_from_profile() -> None:
    assert hatch_cli.enabled_capabilities_for_profile("core") == []
    assert hatch_cli.enabled_capabilities_for_profile("browser") == ["browser"]
    assert hatch_cli.enabled_capabilities_for_profile("local-embeddings") == ["local-embeddings"]
    assert hatch_cli.enabled_capabilities_for_profile("full") == [
        "browser",
        "local-embeddings",
        "perception",
        "advanced-coach",
    ]


@pytest.mark.parametrize(
    ("backend_profile", "local", "expected_files"),
    [
        ("core", False, ["docker-compose.easy.yml"]),
        ("browser", False, ["docker-compose.easy.yml", "docker-compose.browser.yml"]),
        (
            "local-embeddings",
            False,
            ["docker-compose.easy.yml", "docker-compose.local-embeddings.yml"],
        ),
        ("full", False, ["docker-compose.easy.yml", "docker-compose.full.yml"]),
        ("core", True, ["docker-compose.easy.yml", "docker-compose.local-ai.yml"]),
        (
            "local-embeddings",
            True,
            [
                "docker-compose.easy.yml",
                "docker-compose.local-embeddings.yml",
                "docker-compose.local-ai.yml",
            ],
        ),
        (
            "full",
            True,
            ["docker-compose.easy.yml", "docker-compose.full.yml", "docker-compose.local-ai.yml"],
        ),
    ],
)
def test_compose_files_include_backend_profile_and_local_ai_independently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_profile: str,
    local: bool,
    expected_files: list[str],
) -> None:
    configure_home(tmp_path, monkeypatch)

    args = hatch_cli.compose_files(local=local, backend_profile=backend_profile)

    assert _compose_file_names(args) == expected_files


def test_compose_files_preserve_local_model_profiles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_home(tmp_path, monkeypatch)
    hatch_cli.ensure_home()
    hatch_cli.write_json(
        hatch_cli.RUNTIME_PATH,
        {
            "ai_mode": "local",
            "primary_model_id": "primary",
            "triage_model_id": "triage",
        },
    )

    args = hatch_cli.compose_files(backend_profile="browser")

    assert _compose_file_names(args) == [
        "docker-compose.easy.yml",
        "docker-compose.browser.yml",
        "docker-compose.local-ai.yml",
    ]
    assert _compose_profiles(args) == ["local-primary", "local-triage"]


def test_capabilities_enable_no_restart_persists_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_home(tmp_path, monkeypatch)
    calls: list[list[str]] = []
    monkeypatch.setattr(hatch_cli, "run", lambda command, **_: calls.append(command))
    args = type("Args", (), {
        "profile": "browser",
        "yes": True,
        "no_restart": True,
        "restart_all": False,
    })()

    hatch_cli.cmd_capabilities_enable(args)

    assert hatch_cli.read_backend_capabilities()["profile"] == "browser"
    assert calls == []


def test_capabilities_enable_recreates_backend_only_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_home(tmp_path, monkeypatch)
    calls: list[list[str]] = []
    monkeypatch.setattr(hatch_cli, "run", lambda command, **_: calls.append(command))
    args = type("Args", (), {
        "profile": "local-embeddings",
        "yes": True,
        "no_restart": False,
        "restart_all": False,
    })()

    hatch_cli.cmd_capabilities_enable(args)

    assert hatch_cli.read_backend_capabilities()["profile"] == "local-embeddings"
    command = calls[-1]
    assert _compose_file_names(command) == [
        "docker-compose.easy.yml",
        "docker-compose.local-embeddings.yml",
    ]
    assert command[-4:] == ["up", "-d", "--build", "backend"]


def test_capabilities_disable_returns_to_core_without_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_home(tmp_path, monkeypatch)
    hatch_cli.write_backend_capabilities("full", updated_by="test")
    args = type("Args", (), {"yes": True, "no_restart": True, "restart_all": False})()

    hatch_cli.cmd_capabilities_disable(args)

    assert hatch_cli.read_backend_capabilities()["profile"] == "core"


def test_capabilities_parser_rejects_conflicting_restart_flags() -> None:
    with pytest.raises(SystemExit):
        hatch_cli.parser().parse_args(
            [
                "capabilities",
                "enable",
                "browser",
                "--no-restart",
                "--restart-all",
            ]
        )


def test_status_reports_backend_capability_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_home(tmp_path, monkeypatch)
    hatch_cli.write_backend_capabilities("full", updated_by="test")
    monkeypatch.setattr(
        hatch_cli,
        "run",
        lambda *_, **__: type("Result", (), {"returncode": 0, "stdout": ""})(),
    )
    monkeypatch.setattr(hatch_cli, "catalog", lambda: [])

    hatch_cli.cmd_status(type("Args", (), {})())

    output = capsys.readouterr().out
    assert "Backend capability profile: full" in output
    assert "Browser automation: installed" in output


def test_update_validates_selected_backend_profile_compose_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_home(tmp_path, monkeypatch)
    hatch_cli.ensure_home()
    hatch_cli.write_json(
        hatch_cli.INSTALL_PATH,
        {"managed": True, "source_dir": str(hatch_cli.ROOT)},
    )
    hatch_cli.write_backend_capabilities("full", updated_by="test")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> object:
        calls.append(command)
        if command == ["git", "status", "--porcelain"]:
            return type("Result", (), {"returncode": 0, "stdout": ""})()
        return type("Result", (), {"returncode": 0, "stdout": ""})()

    monkeypatch.setattr(hatch_cli, "run", fake_run)
    monkeypatch.setattr(hatch_cli.shutil, "copytree", lambda *_, **__: None)
    args = type("Args", (), {"dry_run": False, "no_restart": True})()

    hatch_cli.cmd_update(args)

    config_command = next(command for command in calls if command[-2:] == ["config", "--quiet"])
    assert _compose_file_names(config_command) == [
        "docker-compose.easy.yml",
        "docker-compose.full.yml",
    ]


def test_install_scripts_and_readme_document_backend_profile_flow() -> None:
    install_sh = (ROOT / "install.sh").read_text(encoding="utf-8")
    install_ps1 = (ROOT / "install.ps1").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "--backend-profile" in install_sh
    assert "backend_capabilities.json" in install_sh
    assert "docker-compose.browser.yml" in install_sh
    assert "-BackendProfile" in install_ps1
    assert "backend_capabilities.json" in install_ps1
    assert "LocalEmbeddings" in install_ps1
    for expected in (
        "hatch capabilities status",
        "hatch capabilities enable browser",
        "hatch capabilities enable local-embeddings",
        "hatch capabilities enable full",
        "hatch capabilities disable",
        "./install.sh --mode advanced --backend-profile full",
        ".\\install.ps1 -Mode advanced -BackendProfile full",
    ):
        assert expected in readme


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
