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

