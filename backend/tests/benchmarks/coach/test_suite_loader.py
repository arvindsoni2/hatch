from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from benchmarks.coach.suite_loader import (
    SuitePrivacyError,
    SuiteValidationError,
    hash_file,
    load_suite,
)

ROOT = Path(__file__).resolve().parents[4]
V1_SUITE = ROOT / "backend" / "benchmarks" / "coach" / "fixtures" / "v1"

EXPECTED_SCENARIOS = {
    "cr_01_grounded_synthesis",
    "cr_02_conflicting_sources",
    "cr_03_injection_resistance",
    "qg_01_requirement_coverage",
    "qg_02_injection_resistance",
    "ma_01_supported_star",
    "ma_02_insufficient_evidence",
    "ae_01_strong_answer",
    "ae_02_weak_answer",
    "ae_03_metric_grounding",
    "ae_h01_provider_unavailable",
    "ae_h02_malformed_output",
    "rb_01_score_immutability",
    "sr_01_mixed_session_report",
    "sr_02_provider_fallback",
    "td_01_technical_drill",
    "e2e_01_three_question_session",
}


def _copy_suite(tmp_path: Path) -> Path:
    target = tmp_path / "v1"
    shutil.copytree(V1_SUITE, target)
    shutil.copy(V1_SUITE.parent / "stopwords_en.txt", tmp_path / "stopwords_en.txt")
    return target


def _rewrite(path: Path, mutate) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def test_v1_suite_loads_all_required_scenarios_and_hashes() -> None:
    suite = load_suite(V1_SUITE)
    assert suite.suite_id == "hatch-coach-model-quality-v1"
    assert suite.version == "1"
    assert set(suite.scenarios) == EXPECTED_SCENARIOS
    assert set(suite.input_hashes) == set(suite.declared_files)
    assert suite.input_hashes["job_description.txt"] == hash_file(
        V1_SUITE / "job_description.txt"
    )


def test_v1_suite_has_five_unique_loopback_models_and_two_seeds() -> None:
    suite = load_suite(V1_SUITE)
    assert {model.id for model in suite.models} == {
        "qwen35-4b",
        "qwen35-9b",
        "qwen3-8b",
        "gemma4-e2b",
        "gemma4-e4b",
    }
    assert suite.seeds == (11, 23)
    assert all(model.endpoint.host in {"127.0.0.1", "localhost", "::1", "[::1]"} for model in suite.models)


@pytest.mark.parametrize(
    "scenario_id",
    [
        "ae_h01_provider_unavailable",
        "ae_h02_malformed_output",
        "sr_02_provider_fallback",
    ],
)
def test_mandatory_forced_failures_are_harness_contract(scenario_id: str) -> None:
    scenario = load_suite(V1_SUITE).scenario(scenario_id)
    assert scenario.qualification_scope == "harness_contract"
    assert scenario.forced_failure is not None


def test_forced_failure_labelled_model_capability_is_rejected(tmp_path: Path) -> None:
    suite_dir = _copy_suite(tmp_path)
    path = suite_dir / "scenarios" / "ae_h01_provider_unavailable.json"
    _rewrite(path, lambda value: value.update(qualification_scope="model_capability"))
    with pytest.raises(SuiteValidationError, match="forced failures must be harness_contract"):
        load_suite(suite_dir)


def test_unknown_scenario_field_is_rejected(tmp_path: Path) -> None:
    suite_dir = _copy_suite(tmp_path)
    path = suite_dir / "scenarios" / "ae_01_strong_answer.json"
    _rewrite(path, lambda value: value.update(unknown=True))
    with pytest.raises(SuiteValidationError, match="Extra inputs are not permitted"):
        load_suite(suite_dir)


def test_stage_inapplicable_input_field_is_rejected(tmp_path: Path) -> None:
    suite_dir = _copy_suite(tmp_path)
    path = suite_dir / "scenarios" / "ae_01_strong_answer.json"

    def add_company_research_input(value: dict[str, object]) -> None:
        scenario_input = value["input"]
        assert isinstance(scenario_input, dict)
        scenario_input["source_bundle"] = "company_research_sources.json"

    _rewrite(path, add_company_research_input)
    with pytest.raises(SuiteValidationError, match="input fields not allowed"):
        load_suite(suite_dir)


def test_undeclared_fixture_file_is_rejected(tmp_path: Path) -> None:
    suite_dir = _copy_suite(tmp_path)
    (suite_dir / "scenarios" / "extra.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(SuiteValidationError, match="undeclared fixture files"):
        load_suite(suite_dir)


def test_personal_email_is_rejected_without_echoing_value(tmp_path: Path) -> None:
    suite_dir = _copy_suite(tmp_path)
    path = suite_dir / "candidate_evidence.json"
    _rewrite(path, lambda value: value.update(email="person@gmail.com"))
    with pytest.raises(SuitePrivacyError) as exc_info:
        load_suite(suite_dir)
    assert "prohibited public fixture content" in str(exc_info.value)
    assert "person@gmail.com" not in str(exc_info.value)


def test_candidate_evidence_id_must_match_existing_stable_rule(tmp_path: Path) -> None:
    suite_dir = _copy_suite(tmp_path)
    path = suite_dir / "candidate_evidence.json"

    def replace_id(value: dict[str, object]) -> None:
        evidence = value["evidence"]
        assert isinstance(evidence, list)
        assert isinstance(evidence[0], dict)
        evidence[0]["evidence_id"] = "readable-but-not-stable"

    _rewrite(path, replace_id)
    with pytest.raises(SuiteValidationError, match="stable evidence id"):
        load_suite(suite_dir)


def test_scenario_evidence_references_must_exist(tmp_path: Path) -> None:
    suite_dir = _copy_suite(tmp_path)
    path = suite_dir / "scenarios" / "ma_01_supported_star.json"

    def replace_reference(value: dict[str, object]) -> None:
        expected = value["expected"]
        assert isinstance(expected, dict)
        expected["required_evidence_ids"] = ["unknown-evidence-id"]

    _rewrite(path, replace_reference)
    with pytest.raises(SuiteValidationError, match="unknown evidence id"):
        load_suite(suite_dir)


def test_absolute_protected_path_is_rejected(tmp_path: Path) -> None:
    suite_dir = _copy_suite(tmp_path)
    path = suite_dir / "company_research.json"
    _rewrite(path, lambda value: value.update(cache_path="/home/person/profile.yaml"))
    with pytest.raises(SuitePrivacyError, match="prohibited public fixture content"):
        load_suite(suite_dir)


def test_private_benchmark_area_remains_ignored() -> None:
    ignore_text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/benchmarks/" in ignore_text.splitlines()
