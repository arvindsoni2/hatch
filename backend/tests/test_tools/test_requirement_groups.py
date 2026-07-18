"""Requirement group tripwires for the lightweight backend image work."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]

REQUIRED_GROUPS = {
    "requirements-core.txt",
    "requirements-browser.txt",
    "requirements-local-ai.txt",
    "requirements-observability.txt",
    "requirements-perception.txt",
    "requirements-full.txt",
}

CORE_FORBIDDEN_PACKAGES = {
    "faster-whisper",
    "playwright",
    "sentence-transformers",
    "tokenizers",
    "torch",
    "transformers",
    "opentelemetry-api",
    "opentelemetry-sdk",
    "opentelemetry-exporter-otlp-proto-grpc",
    "opentelemetry-instrumentation-fastapi",
    "opentelemetry-instrumentation-logging",
}


def _requirement_lines(path: Path) -> list[str]:
    return [
        line.split("#", 1)[0].strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    ]


def _package_name(requirement: str) -> str:
    if requirement.startswith("-r "):
        return requirement
    for separator in ("==", ">=", "<=", "~=", "!=", ">", "<", "["):
        if separator in requirement:
            return requirement.split(separator, 1)[0].strip().lower()
    return requirement.strip().lower()


def _package_names(path: Path) -> set[str]:
    return {
        _package_name(requirement)
        for requirement in _requirement_lines(path)
        if not requirement.startswith("--")
    }


def test_requirement_group_files_exist() -> None:
    """The dependency split must be explicit before Docker targets consume it."""
    missing = sorted(name for name in REQUIRED_GROUPS if not (BACKEND_DIR / name).is_file())

    assert missing == []


def test_core_requirements_exclude_optional_heavy_packages() -> None:
    """Core backend dependencies must stay free of browser/ML/perception packages."""
    packages = _package_names(BACKEND_DIR / "requirements-core.txt")

    assert packages.isdisjoint(CORE_FORBIDDEN_PACKAGES)


def test_current_default_requirements_remain_full_runtime_contract() -> None:
    """This PR prepares the split without changing the existing Docker install set."""
    packages = _package_names(BACKEND_DIR / "requirements.txt")

    assert {"playwright", "sentence-transformers", "transformers"}.issubset(packages)


def test_optional_requirement_groups_reference_core() -> None:
    """Optional groups extend core instead of duplicating the default runtime list."""
    for name in (
        "requirements-browser.txt",
        "requirements-local-ai.txt",
        "requirements-observability.txt",
    ):
        lines = _requirement_lines(BACKEND_DIR / name)

        assert lines[0] == "-r requirements-core.txt"


def test_full_requirements_include_all_capability_groups() -> None:
    """The full image/audit path must keep every optional capability visible."""
    lines = _requirement_lines(BACKEND_DIR / "requirements-full.txt")

    assert "-r requirements-core.txt" in lines
    assert "-r requirements-browser.txt" in lines
    assert "-r requirements-local-ai.txt" in lines
    assert "-r requirements-observability.txt" in lines
    assert "-r requirements-perception.txt" in lines


def test_optional_dependency_modules_import_without_optional_packages() -> None:
    """Core startup-sensitive modules must tolerate absent heavy packages."""
    code = """
import builtins
import importlib

blocked = {
    "faster_whisper",
    "playwright",
    "sentence_transformers",
    "torch",
    "transformers",
}
real_import = builtins.__import__

def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name.split(".", 1)[0] in blocked:
        raise ImportError(f"blocked optional dependency: {name}")
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = guarded_import

for module_name in (
    "app.agents.scorer_agent",
    "app.agents.tools.embedder",
    "app.agents.tools.semantic_scorer",
    "app.scrapers.registry",
    "app.services.transcriber",
    "app.services.voice_emotion_analyser",
):
    importlib.import_module(module_name)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
