"""Strict loading and privacy checks for the committed Coach benchmark suite."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import Field, ValidationError, model_validator

from benchmarks.contracts import ModelSpec, StrictModel

from .contracts import CoachScenario

_COMMON_PERSONAL_EMAILS = re.compile(
    r"@[a-z0-9.-]*(?:gmail|outlook|hotmail|yahoo)\.[a-z]{2,}", re.IGNORECASE
)
_SECRET_KEY = re.compile(
    r"(?:^|[_-])(?:api[_-]?key|access[_-]?token|auth(?:orization)?|password|secret)(?:$|[_-])",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(
    r"(?:bearer\s+[a-z0-9._-]{8,}|sk-[a-z0-9_-]{8,})", re.IGNORECASE
)
_WINDOWS_ABSOLUTE = re.compile(r"^[a-zA-Z]:[\\/]")
_KNOWN_PRIVATE_MARKERS = ("arvind soni",)
_STAGE_INPUT_FIELDS = {
    "company_research": {
        "company_name",
        "sector",
        "source_bundle",
        "conflicting_source_ids",
        "attack_source_id",
    },
    "question_generation": {
        "question_count",
        "difficulty",
        "company_name",
        "role_title",
    },
    "model_answer": {
        "question",
        "category",
        "difficulty",
        "company_name",
        "evidence_ids",
    },
    "answer_evaluation": {
        "question",
        "category",
        "transcript",
        "model_answer_evidence_ids",
        "speech_metrics",
    },
    "rubric_synthesis": {"transcript", "baseline_scores", "focus_dimensions"},
    "session_report": {
        "session_id",
        "role_title",
        "company_name",
        "authoritative_report",
    },
    "technical_drill": {"question_id", "question", "category", "requirement_id"},
    "end_to_end": {"company_name", "role_title", "question_count", "answers"},
}


class SuiteValidationError(ValueError):
    """Raised when fixture structure or cross-file references are invalid."""


class SuitePrivacyError(SuiteValidationError):
    """Raised when a public fixture contains prohibited content."""


class _SuiteManifest(StrictModel):
    suite_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    seeds: tuple[int, ...] = Field(min_length=2)
    models_file: str = "models.json"
    candidate_evidence_file: str = "candidate_evidence.json"
    job_description_file: str = "job_description.txt"
    company_research_file: str = "company_research.json"
    company_research_sources_file: str = "company_research_sources.json"
    stopwords_file: str = "../stopwords_en.txt"
    scenario_files: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_seeds_and_scenarios(self) -> "_SuiteManifest":
        if len(self.seeds) != len(set(self.seeds)):
            raise ValueError("suite seeds must be unique")
        if len(self.scenario_files) != len(set(self.scenario_files)):
            raise ValueError("scenario file paths must be unique")
        return self

    def file_names(self) -> tuple[str, ...]:
        return (
            "suite.json",
            self.models_file,
            self.candidate_evidence_file,
            self.job_description_file,
            self.company_research_file,
            self.company_research_sources_file,
            self.stopwords_file,
            *self.scenario_files,
        )


class _ModelsFile(StrictModel):
    models: list[ModelSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_models(self) -> "_ModelsFile":
        ids = [item.id for item in self.models]
        if len(ids) != len(set(ids)):
            raise ValueError("model ids must be unique")
        return self


@dataclass(frozen=True)
class LoadedCoachSuite:
    suite_id: str
    version: str
    seeds: tuple[int, ...]
    models: tuple[ModelSpec, ...]
    scenarios: dict[str, CoachScenario]
    candidate_evidence: dict[str, Any]
    job_description: str
    company_research: dict[str, Any]
    company_research_sources: dict[str, Any]
    stopwords: frozenset[str]
    input_hashes: dict[str, str]
    declared_files: tuple[str, ...]
    root: Path

    def scenario(self, scenario_id: str) -> CoachScenario:
        try:
            return self.scenarios[scenario_id]
        except KeyError as exc:
            raise SuiteValidationError(f"unknown Coach scenario: {scenario_id}") from exc


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SuiteValidationError(f"invalid Coach fixture JSON: {path.name}") from exc


def _resolve_declared(root: Path, relative: str) -> Path:
    fixture_root = root.parent.resolve()
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(fixture_root):
        raise SuiteValidationError("fixture path escapes the Coach fixture directory")
    return resolved


def _privacy_findings(value: Any, *, key: str = "") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            if _SECRET_KEY.search(str(child_key)):
                findings.append("secret-key")
            findings.extend(_privacy_findings(child_value, key=str(child_key)))
        return findings
    if isinstance(value, list | tuple | set):
        for item in value:
            findings.extend(_privacy_findings(item, key=key))
        return findings
    if not isinstance(value, str):
        return findings

    normalized = value.casefold()
    if any(marker in normalized for marker in _KNOWN_PRIVATE_MARKERS):
        findings.append("private-identity")
    if _COMMON_PERSONAL_EMAILS.search(value):
        findings.append("personal-email")
    if _SECRET_VALUE.search(value):
        findings.append("secret-value")
    if value.startswith("/") or _WINDOWS_ABSOLUTE.match(value):
        findings.append("absolute-path")
    if key.casefold() == "email" and value and not normalized.endswith("@example.test"):
        findings.append("non-synthetic-email")
    return findings


def _declared_root_files(manifest: _SuiteManifest) -> set[str]:
    return {
        name
        for name in manifest.file_names()
        if not name.startswith("../")
    }


def load_suite(path: Path | str) -> LoadedCoachSuite:
    root = Path(path).expanduser().resolve()
    manifest_path = root / "suite.json"
    if not manifest_path.is_file():
        raise SuiteValidationError("Coach suite is missing suite.json")
    try:
        manifest = _SuiteManifest.model_validate(_read_json(manifest_path))
    except ValidationError as exc:
        raise SuiteValidationError(f"invalid Coach suite manifest: {exc}") from exc

    declared = manifest.file_names()
    resolved = {name: _resolve_declared(root, name) for name in declared}
    missing = [name for name, file_path in resolved.items() if not file_path.is_file()]
    if missing:
        raise SuiteValidationError(
            "missing Coach fixture files: " + ", ".join(sorted(missing))
        )

    discovered = {
        item.relative_to(root).as_posix()
        for item in root.rglob("*")
        if item.is_file()
    }
    undeclared = discovered - _declared_root_files(manifest)
    if undeclared:
        raise SuiteValidationError(
            "undeclared fixture files: " + ", ".join(sorted(undeclared))
        )

    raw_values: dict[str, Any] = {}
    for name, file_path in resolved.items():
        raw_values[name] = (
            file_path.read_text(encoding="utf-8")
            if file_path.suffix == ".txt"
            else _read_json(file_path)
        )
    findings = _privacy_findings(raw_values)
    if findings:
        categories = ", ".join(sorted(set(findings)))
        raise SuitePrivacyError(
            f"prohibited public fixture content ({categories}; {len(findings)} finding(s))"
        )

    try:
        models_file = _ModelsFile.model_validate(raw_values[manifest.models_file])
        parsed_scenarios = [
            CoachScenario.model_validate(raw_values[name])
            for name in manifest.scenario_files
        ]
    except ValidationError as exc:
        raise SuiteValidationError(f"invalid Coach fixture contract: {exc}") from exc

    scenario_ids = [item.scenario_id for item in parsed_scenarios]
    if len(scenario_ids) != len(set(scenario_ids)):
        raise SuiteValidationError("Coach scenario ids must be unique")
    scenarios = {item.scenario_id: item for item in parsed_scenarios}
    for scenario in parsed_scenarios:
        unexpected = set(scenario.input) - _STAGE_INPUT_FIELDS[scenario.stage]
        if unexpected:
            raise SuiteValidationError(
                f"{scenario.scenario_id} input fields not allowed for {scenario.stage}: "
                + ", ".join(sorted(unexpected))
            )
    mandatory_harness = {
        "ae_h01_provider_unavailable",
        "ae_h02_malformed_output",
        "sr_02_provider_fallback",
    }
    missing_harness = mandatory_harness - set(scenarios)
    if missing_harness:
        raise SuiteValidationError(
            "missing mandatory harness scenarios: " + ", ".join(sorted(missing_harness))
        )
    for scenario_id in mandatory_harness:
        scenario = scenarios[scenario_id]
        if scenario.qualification_scope != "harness_contract" or not scenario.forced_failure:
            raise SuiteValidationError(
                f"{scenario_id} must declare a harness_contract forced failure"
            )

    candidate = raw_values[manifest.candidate_evidence_file]
    research = raw_values[manifest.company_research_file]
    research_sources = raw_values[manifest.company_research_sources_file]
    if not all(isinstance(item, dict) for item in (candidate, research, research_sources)):
        raise SuiteValidationError("Coach evidence and research fixtures must be objects")

    return LoadedCoachSuite(
        suite_id=manifest.suite_id,
        version=manifest.version,
        seeds=manifest.seeds,
        models=tuple(models_file.models),
        scenarios=scenarios,
        candidate_evidence=candidate,
        job_description=str(raw_values[manifest.job_description_file]),
        company_research=research,
        company_research_sources=research_sources,
        stopwords=frozenset(str(raw_values[manifest.stopwords_file]).splitlines()),
        input_hashes={name: hash_file(file_path) for name, file_path in resolved.items()},
        declared_files=declared,
        root=root,
    )
