"""Requirement group tripwires for the lightweight backend image work."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version

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


def _requirement(path: Path, package_name: str) -> Requirement:
    for requirement_line in _requirement_lines(path):
        if requirement_line.startswith("-r "):
            continue
        requirement = Requirement(requirement_line)
        if requirement.name.lower() == package_name:
            return requirement
    raise AssertionError(f"{package_name} is not declared in {path.name}")


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


def test_canonical_requirements_align_with_secure_transformers_5_runtime() -> None:
    """Every direct declaration must share the secure Transformers 5 solution."""
    default_path = BACKEND_DIR / "requirements.txt"
    perception_path = BACKEND_DIR / "requirements-perception.txt"
    local_ai_path = BACKEND_DIR / "requirements-local-ai.txt"
    transformers_requirements = (
        _requirement(default_path, "transformers"),
        _requirement(local_ai_path, "transformers"),
        _requirement(perception_path, "transformers"),
    )
    perception_tokenizers = _requirement(perception_path, "tokenizers")

    secure_transformers_floor = Version("5.5")
    vulnerable_transformers_version = Version("5.4.0")
    transformers_next_major = Version("6.0")
    compatible_tokenizer_versions = (Version("0.22.0"), Version("0.23.0"))
    incompatible_tokenizer_versions = (Version("0.21.9"), Version("0.23.1"))

    assert all(
        secure_transformers_floor in requirement.specifier
        for requirement in transformers_requirements
    )
    assert all(
        vulnerable_transformers_version not in requirement.specifier
        for requirement in transformers_requirements
    )
    assert all(
        transformers_next_major not in requirement.specifier
        for requirement in transformers_requirements
    )
    assert all(
        version in perception_tokenizers.specifier
        for version in compatible_tokenizer_versions
    )
    assert all(
        version not in perception_tokenizers.specifier
        for version in incompatible_tokenizer_versions
    )


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
    "opentelemetry",
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
    "app.main",
    "app.observability",
    "app.observability.logging",
    "app.observability.runtime",
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
