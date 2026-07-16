"""Strict loader for private benchmark cases."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.schemas.tailor import JDAnalysisResult

from .contracts import BenchmarkCase, CaseManifest, ExpectedFacts

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
