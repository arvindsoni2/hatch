from pathlib import Path

import pytest

from benchmarks.coach.profiles import profile_for
from benchmarks.coach.runner import build_schedule
from benchmarks.coach.suite_loader import load_suite

ROOT = Path(__file__).resolve().parents[4]
SUITE = load_suite(ROOT / "backend/benchmarks/coach/fixtures/v1")


def test_standard_two_repetitions_schedule_exact_direct_reports() -> None:
    schedule = build_schedule(SUITE, profile_for("standard"), ["qwen35-4b"])
    assert sum(item.scenario_id == "sr_01_mixed_session_report" for item in schedule) == 2
    assert sum(item.scenario_id == "sr_02_provider_fallback" for item in schedule) == 2
    assert len({item.attempt_id for item in schedule}) == len(schedule)


def test_acceptance_schedule_is_exact_and_uses_first_seed() -> None:
    profile = profile_for("acceptance-smoke")
    schedule = build_schedule(SUITE, profile, ["qwen35-4b"])
    assert tuple(item.scenario_id for item in schedule) == profile.scenario_ids
    assert {item.seed for item in schedule} == {SUITE.seeds[0]}


def test_schedule_rejects_unknown_model() -> None:
    with pytest.raises(ValueError, match="unknown Coach model"):
        build_schedule(SUITE, profile_for("standard"), ["missing"])


def test_standard_schedule_can_meet_v5_stage_evidence_minima() -> None:
    schedule = build_schedule(SUITE, profile_for("standard"), ["qwen35-4b"])
    model_attempts = [
        item for item in schedule if item.qualification_scope == "model_capability"
    ]
    counts = {
        stage: sum(item.stage == stage for item in model_attempts)
        for stage in {
            "question_generation",
            "model_answer",
            "answer_evaluation",
            "company_research",
            "rubric_synthesis",
            "technical_drill",
        }
    }
    assert counts["question_generation"] >= 4
    assert counts["model_answer"] >= 4
    assert counts["answer_evaluation"] >= 8
    assert counts["company_research"] >= 4
    assert counts["rubric_synthesis"] >= 4
    assert counts["technical_drill"] >= 4
