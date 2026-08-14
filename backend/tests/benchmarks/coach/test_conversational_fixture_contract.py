from __future__ import annotations

import json
from pathlib import Path

from benchmarks.coach.suite_loader import load_suite

ROOT = Path(__file__).resolve().parents[4]
CONVERSATIONAL_SUITE = ROOT / "backend/benchmarks/coach/fixtures/conversational_v1"
REQUIRED_GROUPS = {
    "rubric",
    "evidence_grounding",
    "follow_up",
    "coaching",
    "prohibited_inference",
    "end_to_end",
}


def test_conversational_suite_declares_required_groups_and_only_synthetic_data() -> (
    None
):
    suite = load_suite(CONVERSATIONAL_SUITE)

    assert suite.suite_id == "coach_conversational_v1"
    assert {scenario.group for scenario in suite.scenarios.values()} == REQUIRED_GROUPS
    assert all(
        scenario.qualification_scope == "harness_contract"
        for scenario in suite.scenarios.values()
    )
    assert all(
        "synthetic" in scenario.description.casefold()
        for scenario in suite.scenarios.values()
    )
    fixture_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in CONVERSATIONAL_SUITE.rglob("*.json")
    ).casefold()
    assert "gmail.com" not in fixture_text
    assert "bearer " not in fixture_text
    assert "sk-" not in fixture_text


def test_conversational_suite_has_one_acceptance_case_per_required_group() -> None:
    suite = load_suite(CONVERSATIONAL_SUITE)
    selected = [item for item in suite.scenarios.values() if item.acceptance_smoke]

    assert {item.group for item in selected} == REQUIRED_GROUPS
    assert len(selected) == len(REQUIRED_GROUPS)
    manifest = json.loads((CONVERSATIONAL_SUITE / "suite.json").read_text())
    assert len(manifest["scenario_files"]) == len(suite.scenarios)


def test_conversational_suite_covers_fail_closed_pr3_contract_cases() -> None:
    suite = load_suite(CONVERSATIONAL_SUITE)
    cases = {
        (scenario.group, scenario.input.get("case"))
        for scenario in suite.scenarios.values()
    }

    assert {
        ("rubric", "strong"),
        ("rubric", "vague"),
        ("rubric", "span_invalid"),
        ("rubric", "technical_failure"),
        ("rubric", "prohibited"),
        ("evidence_grounding", "supported"),
        ("evidence_grounding", "partial"),
        ("evidence_grounding", "not_found"),
        ("evidence_grounding", "conflict"),
        ("evidence_grounding", "invalid_id"),
        ("follow_up", "admitted"),
        ("follow_up", "duplicate"),
        ("follow_up", "no_gap"),
        ("follow_up", "third"),
        ("coaching", "safe"),
        ("coaching", "invented_fact"),
    } <= cases
