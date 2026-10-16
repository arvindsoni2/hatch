"""The conversational benchmark must include the persisted report path."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from benchmarks.coach.production_adapter import (
    CoachProductionAdapter,
    DeterministicCoachClient,
    ScenarioContext,
)
from benchmarks.coach.suite_loader import load_suite


SUITE = Path(__file__).resolve().parents[3] / "benchmarks/coach/fixtures/conversational_v1"


@pytest.mark.asyncio
async def test_end_to_end_builds_persists_and_reads_a_valid_report():
    suite = load_suite(SUITE)
    scenario = suite.scenarios["end_to_end_grounded_follow_up"]
    context = ScenarioContext.from_suite(suite)
    client = DeterministicCoachClient(scenario, context, "deterministic-contract")

    execution = await asyncio.wait_for(
        CoachProductionAdapter().execute(scenario, client, context), timeout=15
    )

    assert execution.output["persistence"] == {
        "planned_questions": 2,
        "accepted_attempts": 2,
        "report_snapshot": True,
        "report_read_valid": True,
    }


@pytest.mark.asyncio
async def test_end_to_end_fails_when_report_builder_is_disconnected(monkeypatch):
    from app.services import coach_conversational_report

    suite = load_suite(SUITE)
    scenario = suite.scenarios["end_to_end_grounded_follow_up"]
    context = ScenarioContext.from_suite(suite)
    client = DeterministicCoachClient(scenario, context, "deterministic-contract")

    def disconnected(*args, **kwargs):
        raise RuntimeError("disconnected report build")

    monkeypatch.setattr(coach_conversational_report, "build_conversational_report", disconnected)
    with pytest.raises(RuntimeError, match="disconnected report build"):
        await asyncio.wait_for(
            CoachProductionAdapter().execute(scenario, client, context), timeout=15
        )


@pytest.mark.asyncio
async def test_end_to_end_rejects_invalid_persisted_report(monkeypatch):
    from app.services import coach_conversational_report

    suite = load_suite(SUITE)
    scenario = suite.scenarios["end_to_end_grounded_follow_up"]
    context = ScenarioContext.from_suite(suite)
    client = DeterministicCoachClient(scenario, context, "deterministic-contract")
    monkeypatch.setattr(
        coach_conversational_report,
        "build_conversational_report",
        lambda _: SimpleNamespace(
            persisted_json=lambda: {"session_id": "benchmark-e2e"},
            report_state="completed",
        ),
    )

    with pytest.raises(ValidationError):
        await asyncio.wait_for(
            CoachProductionAdapter().execute(scenario, client, context), timeout=15
        )
