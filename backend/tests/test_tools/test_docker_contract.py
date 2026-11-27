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


def _backend_service(path: str) -> dict:
    return _compose(path)["services"]["backend"]


def test_backend_dockerfile_exposes_expected_runtime_targets() -> None:
    """Future compose files should be able to select explicit backend targets."""
    text = _dockerfile_text()

    for target in ("core", "browser", "local-ai", "observability", "full"):
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
        backend = _backend_service(compose_file)

        assert backend["image"] == "hatch-backend:latest"
        assert backend["build"]["context"] == "./backend"
        assert backend["build"]["dockerfile"] == "Dockerfile"
        assert backend["build"]["target"] == "core"


def test_optional_backend_override_files_select_non_default_targets() -> None:
    """Advanced backend capabilities should be opt-in Compose overlays."""
    expected = {
        "docker-compose.browser.yml": ("hatch-backend:browser", "browser"),
        "docker-compose.local-embeddings.yml": ("hatch-backend:local-ai", "local-ai"),
        "docker-compose.observability.yml": (
            "hatch-backend:observability",
            "observability",
        ),
        "docker-compose.full.yml": ("hatch-backend:full", "full"),
    }

    for compose_file, (image, target) in expected.items():
        backend = _backend_service(compose_file)

        assert backend["image"] == image
        assert backend["build"]["context"] == "./backend"
        assert backend["build"]["dockerfile"] == "Dockerfile"
        assert backend["build"]["target"] == target


def test_local_ai_overlay_remains_llamacpp_only() -> None:
    """The existing local-AI overlay means llama.cpp services, not embeddings."""
    services = _compose("docker-compose.local-ai.yml")["services"]

    assert "backend" not in services
    assert set(services) == {"llm-primary", "llm-triage", "llm-deep"}
    assert services["llm-deep"]["profiles"] == ["deep"]


FRONTEND_DOCKERFILE = ROOT / "frontend" / "Dockerfile"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
API_TARGETS = ("core", "browser", "local-ai", "observability", "full")
DIGEST_PIN = re.compile(r"@sha256:[0-9a-f]{64}\b")


def _from_lines(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("FROM ")
    ]


def test_every_external_image_from_is_digest_pinned() -> None:
    for dockerfile in (DOCKERFILE, FRONTEND_DOCKERFILE):
        lines = _from_lines(dockerfile)
        stages = {line.rsplit(" AS ", 1)[1].split()[0] for line in lines}
        for line in lines:
            image = line.split()[1]
            if image in stages:
                continue
            assert DIGEST_PIN.search(line), (dockerfile.name, line)


def test_frontend_dockerfile_uses_node_24() -> None:
    from_lines = _from_lines(FRONTEND_DOCKERFILE)

    assert from_lines
    assert all(re.search(r"\bnode:24-alpine@sha256:", line) for line in from_lines), from_lines


def test_ci_uses_node_24_for_both_node_jobs() -> None:
    text = CI_WORKFLOW.read_text(encoding="utf-8")

    assert text.count('node-version: "24"') == 2, text.count('node-version: "24"')


def test_every_api_target_has_node_and_template_modules() -> None:
    text = _dockerfile_text()

    node_stages = [
        line for line in _from_lines(DOCKERFILE)
        if re.search(r"\bnode:24-bookworm-slim@sha256:", line)
    ]
    assert node_stages, "no node:24-bookworm-slim stage"

    runtime_base = _stage(text, "runtime-base")
    assert "COPY --from=node" in runtime_base
    assert "node" in runtime_base

    templates = _stage(text, "templates")
    assert "npm ci --omit=dev" in templates
    assert "package-lock.json" in templates

    assert "FROM core AS default" in text

    for target in API_TARGETS:
        body = _stage(text, target)
        assert "COPY --from=templates" in body, target
        assert "/app/templates/node_modules" in body, target
        assert "--chown=appuser:appuser" in body, target
