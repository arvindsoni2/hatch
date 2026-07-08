"""Static guardrails for container optimisation polish work."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _dockerignore_patterns(path: str) -> set[str]:
    return {
        line.strip()
        for line in _read(path).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_ci_audits_all_runtime_requirement_groups() -> None:
    """Split backend dependency groups should stay visible to dependency audit."""
    ci = _read(".github/workflows/ci.yml")

    for requirement_file in (
        "backend/requirements.txt",
        "backend/requirements-core.txt",
        "backend/requirements-browser.txt",
        "backend/requirements-local-ai.txt",
        "backend/requirements-perception.txt",
        "backend/requirements-full.txt",
    ):
        assert requirement_file in ci


def test_frontend_dockerfile_uses_deterministic_cached_npm_ci() -> None:
    """Frontend builds should use the lockfile path without npm install fallback."""
    dockerfile = _read("frontend/Dockerfile")

    assert dockerfile.startswith("# syntax=docker/dockerfile:1.7\n")
    assert "RUN --mount=type=cache,target=/root/.npm npm ci" in dockerfile
    assert "npm install" not in dockerfile
    assert "--frozen-lockfile" not in dockerfile


def test_backend_dockerignore_excludes_local_build_and_test_artifacts() -> None:
    """Backend build context should not include common local-only artifacts."""
    patterns = _dockerignore_patterns("backend/.dockerignore")

    for pattern in (
        ".git",
        ".gitignore",
        ".coverage",
        "coverage.xml",
        "htmlcov/",
        ".mypy_cache/",
        "*.log",
        ".env.*",
        "!.env.example",
        "models/",
        ".cache/",
        "dist/",
        "build/",
        "*.egg-info/",
    ):
        assert pattern in patterns


def test_frontend_dockerignore_excludes_local_build_and_test_artifacts() -> None:
    """Frontend build context should keep generated output and local envs out."""
    patterns = _dockerignore_patterns("frontend/.dockerignore")

    for pattern in (
        ".git",
        ".gitignore",
        "out/",
        "dist/",
        "build/",
        "coverage/",
        "playwright-report/",
        "test-results/",
        ".vitest/",
        "npm-debug.log*",
        ".env",
        ".env.*",
        "!.env.example",
    ):
        assert pattern in patterns


def test_docker_size_report_script_is_available() -> None:
    """The spec's measurement helper should be executable and cover key views."""
    script = ROOT / "scripts" / "report_docker_sizes.sh"

    assert script.is_file()
    assert os.access(script, os.X_OK)

    text = script.read_text(encoding="utf-8")
    assert "docker images" in text
    assert "docker ps --size" in text
    assert "docker history" in text
    assert "hatch-backend:latest" in text
