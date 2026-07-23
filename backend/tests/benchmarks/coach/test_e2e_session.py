from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.coach.production_adapter import (
    CoachProductionAdapter,
    DeterministicCoachClient,
    ScenarioContext,
)
from benchmarks.coach.suite_loader import load_suite

ROOT = Path(__file__).resolve().parents[4]
SUITE_PATH = ROOT / "backend/benchmarks/coach/fixtures/v1"


@pytest.mark.asyncio
async def test_e2e_01_persists_report_rubric_counts_and_followup_focus() -> None:
    suite = load_suite(SUITE_PATH)
    scenario = suite.scenario("e2e_01_three_question_session")
    context = ScenarioContext.from_suite(suite)

    result = await CoachProductionAdapter().execute(
        scenario,
        DeterministicCoachClient(scenario, context, "contract-smoke"),
        context,
    )

    assert result.diagnostic.stage == "session_report"
    assert result.diagnostic.outcome == "completed"
    assert result.output["report_state"] == "completed"
    assert result.output["question_count_total"] == 3
    assert result.output["question_count_evaluated"] == 2
    assert result.output["question_count_skipped"] == 1
    assert result.output["question_count_unavailable"] == 0
    assert result.output["question_count_unanswered"] == 0
    assert result.output["persistence"]["session_status"] == "completed"
    assert result.output["persistence"]["report_snapshot"] is True
    assert result.output["persistence"]["rubric_snapshot"] is True
    assert result.output["follow_up_focus"] == ["specificity", "impact"]
    assert "database_path" not in result.output


@pytest.mark.asyncio
async def test_e2e_01_does_not_mutate_configured_production_database(tmp_path: Path) -> None:
    from benchmarks.coach.artifacts import hash_sqlite_state

    production = tmp_path / "production.db"
    production.write_bytes(b"protected")
    before = hash_sqlite_state(production)
    suite = load_suite(SUITE_PATH)
    scenario = suite.scenario("e2e_01_three_question_session")
    context = ScenarioContext.from_suite(suite)

    await CoachProductionAdapter().execute(
        scenario,
        DeterministicCoachClient(scenario, context, "contract-smoke"),
        context,
    )

    assert hash_sqlite_state(production) == before
