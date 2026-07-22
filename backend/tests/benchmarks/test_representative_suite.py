from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.case_loader import CaseValidationError, load_suite, suite_case


ROOT = Path(__file__).resolve().parents[3]
SUITE_PATH = (
    ROOT
    / "backend"
    / "benchmarks"
    / "fixtures"
    / "representative_suite.json"
)

EXPECTED_CASES = {
    "delivery-project-manager",
    "ai-software-engineer",
    "solution-architect",
    "career-transition",
    "sparse-cv",
    "detailed-multipage-cv",
    "uk-public-sector",
    "sponsorship-salary",
}

EXPECTED_MODELS = {
    "qwen35-4b",
    "qwen35-9b",
    "qwen3-8b",
    "gemma4-e2b",
    "gemma4-e4b",
}


def test_representative_suite_contains_all_required_cases_models_and_seeds() -> None:
    suite = load_suite(SUITE_PATH)

    assert {case.case_id for case in suite.cases} == EXPECTED_CASES
    assert {model.id for model in suite.models} == EXPECTED_MODELS
    assert suite.seeds == [11, 23, 41, 59, 83]
    assert suite.baseline_model_id == "qwen35-4b"
    assert len(suite.stage_b_case_ids) == 4


def test_stage_b_cases_cover_management_technical_sparse_and_eligibility() -> None:
    suite = load_suite(SUITE_PATH)
    stage_b = {
        case.case_id: case
        for case in suite.cases
        if case.case_id in suite.stage_b_case_ids
    }

    assert set(stage_b) == set(suite.stage_b_case_ids)
    combined_tags = set().union(*(case.risk_tags for case in stage_b.values()))
    assert {
        "management",
        "technical",
        "sparse_evidence",
        "eligibility",
    } <= combined_tags


def test_suite_case_builds_existing_benchmark_case_contract() -> None:
    suite = load_suite(SUITE_PATH)

    case = suite_case(suite, "solution-architect")

    assert case.case_id == "solution-architect"
    assert case.seeds == [11, 23, 41, 59, 83]
    assert {model.id for model in case.models} == EXPECTED_MODELS
    assert case.input_hashes["representative_suite.json"] == suite.suite_hash


def test_fixture_is_synthetic_and_contains_no_known_private_identity() -> None:
    raw = SUITE_PATH.read_text(encoding="utf-8")
    normalized = raw.casefold()

    assert "arvind soni" not in normalized
    assert "@gmail.com" not in normalized
    assert "@outlook.com" not in normalized
    assert "@hotmail.com" not in normalized
    assert normalized.count("@example.test") >= len(EXPECTED_CASES)


def test_loader_rejects_non_synthetic_fixture_identity(tmp_path: Path) -> None:
    payload = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    payload["cases"][0]["master_cv"]["personal"]["email"] = "person@gmail.com"
    path = tmp_path / "unsafe-suite.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CaseValidationError, match="synthetic"):
        load_suite(path)
