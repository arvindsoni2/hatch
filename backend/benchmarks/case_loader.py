"""Strict loader for private benchmark cases."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.schemas.tailor import JDAnalysisResult

from .contracts import (
    BenchmarkCase,
    BenchmarkSuite,
    CaseManifest,
    ExpectedFacts,
)

REQUIRED_CASE_FILES = (
    "case.json",
    "master_cv.json",
    "job_description.txt",
    "jd_analysis.json",
    "expected_facts.json",
)


class CaseValidationError(ValueError):
    """Raised before inference when a benchmark case is incomplete or invalid."""


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaseValidationError(f"Invalid benchmark JSON {path.name}: {exc}") from exc


def load_case(path: Path | str) -> BenchmarkCase:
    source_dir = Path(path).expanduser().resolve()
    missing = [name for name in REQUIRED_CASE_FILES if not (source_dir / name).is_file()]
    if missing:
        raise CaseValidationError(
            "Benchmark case is missing required files: " + ", ".join(missing)
        )

    try:
        manifest = CaseManifest.model_validate(_read_json(source_dir / "case.json"))
        master_cv = _read_json(source_dir / "master_cv.json")
        if not isinstance(master_cv, dict):
            raise CaseValidationError("master_cv.json must contain a JSON object")
        jd_analysis = JDAnalysisResult.model_validate(_read_json(source_dir / "jd_analysis.json"))
        expected_facts = ExpectedFacts.model_validate(
            _read_json(source_dir / "expected_facts.json")
        )
    except ValidationError as exc:
        raise CaseValidationError(f"Invalid benchmark case {source_dir.name}: {exc}") from exc

    job_description = (source_dir / "job_description.txt").read_text(encoding="utf-8").strip()
    if not job_description:
        raise CaseValidationError("job_description.txt must not be empty")

    return BenchmarkCase(
        case_id=manifest.case_id,
        source_dir=source_dir,
        master_cv=master_cv,
        job_description=job_description,
        jd_analysis=jd_analysis,
        expected_facts=expected_facts,
        models=manifest.models,
        seeds=manifest.seeds,
        cv_length_tolerance=manifest.cv_length_tolerance,
        input_hashes={name: hash_file(source_dir / name) for name in REQUIRED_CASE_FILES},
    )


def load_suite(path: Path | str) -> BenchmarkSuite:
    """Load and privacy-check the checked-in representative benchmark suite."""
    source_path = Path(path).expanduser().resolve()
    raw = _read_json(source_path)
    if not isinstance(raw, dict):
        raise CaseValidationError("benchmark suite must contain a JSON object")
    serialized = json.dumps(raw, ensure_ascii=False).casefold()
    forbidden = (
        "arvind soni",
        "@gmail.com",
        "@outlook.com",
        "@hotmail.com",
        "@yahoo.com",
    )
    if any(value in serialized for value in forbidden):
        raise CaseValidationError(
            "benchmark suite must contain synthetic identities only"
        )
    for case in raw.get("cases", []):
        if not isinstance(case, dict):
            continue
        personal = case.get("master_cv", {}).get("personal", {})
        email = personal.get("email", "") if isinstance(personal, dict) else ""
        if email and not str(email).casefold().endswith("@example.test"):
            raise CaseValidationError(
                "benchmark suite must contain synthetic example.test emails"
            )
    raw["suite_hash"] = hash_file(source_path)
    try:
        return BenchmarkSuite.model_validate(raw)
    except ValidationError as exc:
        raise CaseValidationError(
            f"Invalid benchmark suite {source_path.name}: {exc}"
        ) from exc


def suite_case(suite: BenchmarkSuite, case_id: str) -> BenchmarkCase:
    """Convert one checked-in suite case to the existing execution contract."""
    selected = next(
        (candidate for candidate in suite.cases if candidate.case_id == case_id),
        None,
    )
    if selected is None:
        raise CaseValidationError(f"unknown benchmark suite case: {case_id}")
    return BenchmarkCase(
        case_id=selected.case_id,
        source_dir=Path(f"fixture://{suite.suite_id}/{selected.case_id}"),
        master_cv=selected.master_cv,
        job_description=selected.job_description,
        jd_analysis=selected.jd_analysis,
        expected_facts=selected.expected_facts,
        models=suite.models,
        seeds=suite.seeds,
        cv_length_tolerance=selected.cv_length_tolerance,
        input_hashes={"representative_suite.json": suite.suite_hash},
    )
