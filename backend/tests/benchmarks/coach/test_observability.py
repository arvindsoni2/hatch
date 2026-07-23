from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

from app.observability.attributes import (
    BENCHMARK_CASE_ID,
    BENCHMARK_RUN_ID,
    BENCHMARK_SEED,
    COACH_BENCHMARK_STATUS,
    COACH_GATE_CODE,
    COACH_OPERATION,
    COACH_OUTCOME,
    COACH_PROFILE,
    COACH_REPETITION,
    COACH_SUITE_VERSION,
    MODEL_ID,
)
from benchmarks.coach import runner as coach_runner
from benchmarks.coach.runner import RunRequest, run_benchmark

ROOT = Path(__file__).resolve().parents[4]
SUITE_PATH = ROOT / "backend/benchmarks/coach/fixtures/v1"


@pytest.mark.asyncio
async def test_contract_scenarios_emit_bounded_benchmark_hierarchy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    roots: list[dict[str, object]] = []
    stages: list[str] = []
    events: list[tuple[str, dict[str, object]]] = []

    class _Span:
        def __init__(self, attributes):
            self.attributes = attributes

        def set_attribute(self, key, value):
            self.attributes[key] = value

        def add_event(self, name, attributes=None):
            events.append((name, dict(attributes or {})))

        def set_error(self, _code):
            return None

    class _Telemetry:
        @contextmanager
        def workflow_span(self, workflow, attributes=None):
            assert workflow == "coach_benchmark"
            current = dict(attributes or {})
            roots.append(current)
            yield _Span(current)

        @contextmanager
        def coach_stage_span(self, stage, _attributes=None):
            stages.append(stage)
            yield _Span({})

    monkeypatch.setattr(coach_runner, "get_telemetry", lambda: _Telemetry())

    summary = await run_benchmark(
        RunRequest(
            suite_path=SUITE_PATH,
            output_root=tmp_path,
            profile_name="contract-smoke",
            model_ids=("qwen35-4b",),
            command="pytest observability",
        )
    )

    assert len(roots) == summary.terminal
    first = roots[0]
    assert first[COACH_OPERATION] == "benchmark_scenario"
    assert first[BENCHMARK_RUN_ID] == summary.run_id
    assert first[BENCHMARK_CASE_ID] == summary.results[0].attempt.scenario_id
    assert first[BENCHMARK_SEED] == summary.results[0].attempt.seed
    assert first[MODEL_ID] == "qwen35-4b"
    assert first[COACH_REPETITION] == 1
    assert first[COACH_PROFILE] == "contract-smoke"
    assert first[COACH_SUITE_VERSION] == "1"
    assert first[COACH_BENCHMARK_STATUS] == summary.results[0].status
    assert first[COACH_OUTCOME] == summary.results[0].stage_outcome
    assert stages.count("coach.benchmark.scenario") == summary.terminal
    assert stages.count("coach.benchmark.prepare") == summary.terminal
    assert stages.count("coach.benchmark.validate") == summary.terminal
    assert stages.count("coach.benchmark.score") == summary.terminal
    assert stages.count("coach.benchmark.persist") == summary.terminal
    expected_gate_codes = [
        gate.code for result in summary.results for gate in result.gates
    ]
    assert [name for name, _attributes in events] == ["coach_gate"] * len(
        expected_gate_codes
    )
    assert [attributes[COACH_GATE_CODE] for _name, attributes in events] == (
        expected_gate_codes
    )
    telemetry_payload = repr((roots, events))
    assert "Ignore all previous" not in telemetry_payload
    assert "synthetic-candidate" not in telemetry_payload
