from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
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
    monkeypatch.setattr(
        hatch_cli,
        "MODEL_VERIFICATION_PATH",
        tmp_path / "config" / "model_verification.json",
        raising=False,
    )
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
    installer_shell = install_sh + "\n" + "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "scripts" / "installer").glob("*.sh"))
    )
    install_ps1 = (ROOT / "install.ps1").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "--backend-profile" in installer_shell
    assert "backend_capabilities.json" in installer_shell
    assert "docker-compose.browser.yml" in installer_shell
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
        "--non-interactive",
        "--install-docker",
        "--allow-docker-group",
        "Fedora 43/44",
        "docker group grants root-level privileges",
        "${HATCH_HOME}/probe/hardware_probe_latest.json",
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


def test_provider_env_canonicalizes_aliases_and_openrouter() -> None:
    assert hatch_cli.provider_env("google_gemini") == "GOOGLE_API_KEY"
    assert hatch_cli.provider_env("google") == "GOOGLE_API_KEY"
    assert hatch_cli.provider_env("openrouter") == "OPENROUTER_API_KEY"


def test_provider_test_uses_backend_without_reading_or_sending_secret(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}

    class Result:
        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"ok": true, "status": "ready"}'

    def fake_urlopen(request: object, timeout: int):
        captured["request"] = request
        captured["timeout"] = timeout
        return Result()

    monkeypatch.setattr(hatch_cli.urllib.request, "urlopen", fake_urlopen)
    hatch_cli.cmd_provider_test(type("Args", (), {"provider": "anthropic"})())

    request = captured["request"]
    payload = json.loads(request.data)
    assert payload == {"provider": "anthropic"}
    assert "secret" not in request.data.decode().lower()
    assert "ready" in capsys.readouterr().out


def test_probe_writes_only_canonical_snapshot_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_home(tmp_path, monkeypatch)
    monkeypatch.setattr(hatch_cli, "total_ram_gb", lambda: 32.0)
    monkeypatch.setattr(hatch_cli, "model_buckets", lambda *_: {
        "recommended": [], "compatible": [], "not_recommended": [],
    })
    monkeypatch.setattr(hatch_cli, "docker_running", lambda: False)
    monkeypatch.setattr(hatch_cli, "compose_available", lambda: False)
    monkeypatch.setattr(hatch_cli, "port_status", lambda _: "available")

    hatch_cli.cmd_probe(type("Args", (), {})())

    canonical = tmp_path / "probe" / "hardware_probe_latest.json"
    assert json.loads(canonical.read_text())["sanitised"] is True
    assert not (tmp_path / "config" / "hardware_probe_latest.json").exists()


def test_probe_migrates_valid_legacy_snapshot_without_deleting_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_home(tmp_path, monkeypatch)
    hatch_cli.ensure_home()
    legacy = tmp_path / "config" / "hardware_probe_latest.json"
    legacy.write_text(json.dumps({"schema_version": 1, "sanitised": True}))

    migrated = hatch_cli.migrate_legacy_probe()

    assert migrated is True
    assert legacy.exists()
    assert json.loads((tmp_path / "probe" / "hardware_probe_latest.json").read_text())["sanitised"] is True


def test_cloud_runtime_canonicalizes_provider_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_home(tmp_path, monkeypatch)
    hatch_cli.ensure_home()
    hatch_cli.write_json(
        hatch_cli.INTENT_PATH,
        {
            "schema_version": 2,
            "ai_mode": "cloud",
            "cloud_provider": "google_gemini",
            "cloud_primary_model": "gemini-primary",
            "cloud_triage_model": "gemini-triage",
        },
    )
    hatch_cli.write_env({"GOOGLE_API_KEY": "test-value"})
    monkeypatch.setattr(hatch_cli, "compose", lambda *_, **__: None)

    hatch_cli.cmd_apply(type("Args", (), {"no_restart": True})())

    runtime = hatch_cli.read_json(hatch_cli.RUNTIME_PATH, {})
    assert runtime["provider"] == "google_genai"


def test_triage_only_runtime_disables_quality_features(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_home(tmp_path, monkeypatch)
    hatch_cli.ensure_home()
    model = next(item for item in hatch_cli.catalog() if item["role"] == "triage")
    path = hatch_cli.MODELS_DIR / model["filename"]
    path.write_bytes(b"present")
    hatch_cli.write_json(hatch_cli.MODEL_VERIFICATION_PATH, {
        model["id"]: {
            "path": str(path.resolve()),
            "sha256": model["sha256"],
            "revision": model["source_revision"],
            "size_bytes": path.stat().st_size,
        }
    })

    runtime = hatch_cli.runtime_for_local([model["id"]])

    assert runtime["quality_mode"] == "triage_only"
    assert not any(runtime["feature_gates"].values())


def test_models_install_without_explicit_routes_lists_and_exits_usage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_home(tmp_path, monkeypatch)
    monkeypatch.setattr(hatch_cli, "cmd_models_list", lambda _: print("candidate"))

    with pytest.raises(SystemExit) as exc:
        hatch_cli.cmd_models_install(
            type("Args", (), {"primary": None, "triage": None, "yes": True})()
        )

    assert exc.value.code == 2
    output = capsys.readouterr()
    assert "candidate" in output.out
    assert "--primary" in output.err
    assert "--triage" in output.err


def test_catalog_uses_only_current_validated_discovery_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_home(tmp_path, monkeypatch)
    hatch_cli.ensure_home()
    valid = {
        "catalog_id": "hf:publisher/model:file.gguf:abc",
        "filename": "file.gguf",
        "revision": "a" * 40,
        "sha256": "b" * 64,
        "size_bytes": 12,
        "download_size_gb": 0.1,
        "download_url": f"https://huggingface.co/publisher/model/resolve/{'a' * 40}/file.gguf",
    }
    cache_path = hatch_cli.CONFIG_DIR / "model_discovery_cache.json"
    hatch_cli.write_json(cache_path, {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "models": [valid, {**valid, "catalog_id": "invalid", "sha256": "not-a-sha"}],
    })

    ids = {model["id"] for model in hatch_cli.catalog()}
    assert valid["catalog_id"] in ids
    assert "invalid" not in ids

    payload = hatch_cli.read_json(cache_path, {})
    payload["created_at"] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    hatch_cli.write_json(cache_path, payload)
    assert valid["catalog_id"] not in {model["id"] for model in hatch_cli.catalog()}


def test_models_install_preserves_intent_and_writes_verification_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_home(tmp_path, monkeypatch)
    content = b"verified-model"
    digest = hashlib.sha256(content).hexdigest()
    models = [
        {
            "id": "primary-id",
            "display_name": "Primary",
            "filename": "primary.gguf",
            "sha256": digest,
            "size_bytes": len(content),
            "download_size_gb": 0.01,
            "download_url": "https://example.test/primary.gguf",
            "source_revision": "a" * 40,
        },
        {
            "id": "triage-id",
            "display_name": "Triage",
            "filename": "triage.gguf",
            "sha256": digest,
            "size_bytes": len(content),
            "download_size_gb": 0.01,
            "download_url": "https://example.test/triage.gguf",
            "source_revision": "b" * 40,
        },
    ]
    monkeypatch.setattr(hatch_cli, "catalog", lambda: models)
    monkeypatch.setattr(
        hatch_cli.urllib.request,
        "urlretrieve",
        lambda _url, destination: Path(destination).write_bytes(content),
    )
    hatch_cli.ensure_home()
    hatch_cli.write_json(
        hatch_cli.INTENT_PATH,
        {"schema_version": 2, "backend_profile": "full", "experience": "custom"},
    )

    hatch_cli.cmd_models_install(
        type("Args", (), {"primary": "primary-id", "triage": "triage-id", "yes": True})()
    )

    intent = hatch_cli.read_json(hatch_cli.INTENT_PATH, {})
    assert intent["schema_version"] == 2
    assert intent["backend_profile"] == "full"
    assert intent["experience"] == "custom"
    assert intent["local_primary_model"] == "primary-id"
    assert intent["local_triage_model"] == "triage-id"
    manifest = hatch_cli.read_json(hatch_cli.MODEL_VERIFICATION_PATH, {})
    assert set(manifest) == {"primary-id", "triage-id"}
    assert manifest["primary-id"]["sha256"] == digest


def test_fetch_models_without_ids_does_not_download() -> None:
    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "fetch_models.sh")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "hatch models" in result.stderr


def test_easy_local_compose_has_no_fixed_qwen_fallback() -> None:
    text = (ROOT / "docker-compose.local-ai.yml").read_text(encoding="utf-8")

    assert ":-Qwen" not in text
    assert "HATCH_PRIMARY_MODEL_FILE:?" in text
    assert "HATCH_TRIAGE_MODEL_FILE:?" in text


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
