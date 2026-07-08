"""Static Docker/Compose contract tests for backend image split work."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = ROOT / "backend" / "Dockerfile"


def _dockerfile_text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def _stage(text: str, stage_name: str) -> str:
    pattern = re.compile(
        rf"^FROM .* AS {re.escape(stage_name)}\b(?P<body>.*?)(?=^FROM |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    assert match is not None, f"missing Dockerfile stage: {stage_name}"
    return match.group("body")


def _compose(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def test_backend_dockerfile_exposes_expected_runtime_targets() -> None:
    """Future compose files should be able to select explicit backend targets."""
    text = _dockerfile_text()

    for target in ("core", "browser", "local-ai", "full"):
        assert re.search(rf"^FROM .* AS {target}\b", text, re.MULTILINE), target


def test_backend_dockerfile_default_target_is_core() -> None:
    """Plain docker builds should resolve to the lightweight backend target."""
    from_lines = [
        line
        for line in _dockerfile_text().splitlines()
        if line.startswith("FROM ")
    ]

    assert from_lines[-1] == "FROM core AS default"


def test_core_target_uses_core_requirements_only() -> None:
    """The default target must install only the lightweight dependency group."""
    text = _dockerfile_text()
    core_builder = _stage(text, "core-builder")
    core = _stage(text, "core")

    assert "requirements-core.txt" in core_builder
    assert "requirements.txt" not in core_builder
    assert "requirements-browser.txt" not in core_builder
    assert "requirements-local-ai.txt" not in core_builder
    assert "requirements-perception.txt" not in core_builder
    assert "/ms-playwright" not in core
    assert "COPY --from=playwright-stage /usr/lib /usr/lib" not in core
    assert "COPY --from=playwright-stage /lib /lib" not in core


def test_default_compose_files_build_backend_core_target() -> None:
    """Both default startup paths should build the lightweight backend target."""
    for compose_file in ("docker-compose.yml", "docker-compose.easy.yml"):
        backend = _compose(compose_file)["services"]["backend"]

        assert backend["image"] == "hatch-backend:latest"
        assert backend["build"]["context"] == "./backend"
        assert backend["build"]["dockerfile"] == "Dockerfile"
        assert backend["build"]["target"] == "core"
