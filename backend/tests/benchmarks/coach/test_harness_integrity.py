from __future__ import annotations

from pathlib import Path

from app.services.coach_contracts import CoachDiagnostic
from benchmarks.coach.contracts import GateFinding, ScenarioResult, ScheduleEntry
from benchmarks.coach.production_adapter import StageExecution
from benchmarks.coach.runner import _state
from benchmarks.coach.suite_loader import load_suite
from benchmarks.coach.validators import validate_execution

ROOT = Path(__file__).resolve().parents[4]
SUITE_PATH = ROOT / "backend/benchmarks/coach/fixtures/v1"


def _entry(attempt_id: str, scope: str = "harness_contract") -> ScheduleEntry:
    return ScheduleEntry(
        attempt_id=attempt_id,
        model_id="qwen35-4b",
        scenario_id="sr_02_provider_fallback",
        stage="session_report",
        qualification_scope=scope,
        repetition=1,
        seed=17,
    )


def test_harness_scenario_missing_expected_gate_is_blocking() -> None:
    scenario = load_suite(SUITE_PATH).scenario("sr_02_provider_fallback")
    diagnostic = CoachDiagnostic(
        stage="session_report",
        outcome="completed",
        execution_mode="llm",
        prompt_id="session_report",
        prompt_version="2.0.0",
        output_schema_version="1.0.0",
        model_id="bad-harness",
        attempt_count=1,
        repair_count=0,
        gate_codes=[],
        duration_ms=0,
    )
    execution = StageExecution(
        output={
            "report_state": "fallback",
            **scenario.input["authoritative_report"],
        },
        diagnostic=diagnostic,
        provider_attempt_count=1,
        repair_count=0,
    )

    validation = validate_execution(scenario, execution)

    assert "coach_stage_failed" in validation.blocking_codes


def test_terminal_harness_failure_invalidates_run() -> None:
    schedule = (_entry("harness"),)
    result = ScenarioResult(
        attempt=schedule[0],
        status="failed",
        stage_outcome="failed",
        duration_ms=1,
        gates=[GateFinding(code="coach_stage_failed", blocking=True)],
    )

    assert _state(
        schedule,
        [result],
        deadline=False,
        interrupted=False,
        protected_changed=False,
    ) == "invalid_harness_integrity"


def test_terminal_harness_timeout_invalidates_run() -> None:
    schedule = (_entry("harness-timeout"),)
    result = ScenarioResult(
        attempt=schedule[0],
        status="timeout",
        stage_outcome="unavailable",
        duration_ms=1,
        timeout_stage="call",
        gates=[GateFinding(code="coach_stage_timeout", blocking=False)],
    )

    assert _state(
        schedule,
        [result],
        deadline=False,
        interrupted=False,
        protected_changed=False,
    ) == "invalid_harness_integrity"


def test_unstarted_harness_attempt_selects_incomplete_deadline() -> None:
    completed = _entry("model", scope="model_capability")
    unstarted = _entry("harness")
    result = ScenarioResult(
        attempt=completed,
        status="completed",
        stage_outcome="completed",
        duration_ms=1,
    )

    assert _state(
        (completed, unstarted),
        [result],
        deadline=True,
        interrupted=False,
        protected_changed=False,
    ) == "incomplete_deadline"
