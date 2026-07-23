from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from app.services.coach_contracts import CoachDiagnostic
from benchmarks.coach.production_adapter import StageExecution
from benchmarks.coach.runner import RunRequest, RunnerDependencies, run_benchmark
from benchmarks.coach import runner as coach_runner

ROOT = Path(__file__).resolve().parents[4]
SUITE_PATH = ROOT / "backend/benchmarks/coach/fixtures/v1"


class Client:
    def __init__(self, model: str) -> None:
        self.model = model


@asynccontextmanager
async def clients(spec, seed):
    del seed
    yield Client(spec.id)


class ControlledAdapter:
    def __init__(self, delays: dict[str, float] | None = None) -> None:
        self.delays = delays or {}
        self.calls: list[tuple[str, str]] = []

    async def execute(self, scenario, client, context):
        del context
        self.calls.append((client.model, scenario.scenario_id))
        await asyncio.sleep(self.delays.get(f"{client.model}:{scenario.scenario_id}", 0))
        diagnostic = CoachDiagnostic(
            stage=scenario.stage,
            outcome="completed",
            execution_mode="llm",
            prompt_id=scenario.stage,
            prompt_version="1",
            output_schema_version="1",
            model_id=client.model,
            attempt_count=1,
            repair_count=0,
            gate_codes=[],
            duration_ms=0,
        )
        return StageExecution({}, diagnostic, 1, 0)


def request(tmp_path: Path, **changes) -> RunRequest:
    values = {
        "suite_path": SUITE_PATH,
        "output_root": tmp_path,
        "profile_name": "acceptance-smoke",
        "model_ids": ("qwen35-4b",),
        "command": "test",
    }
    values.update(changes)
    return RunRequest(**values)


@pytest.mark.asyncio
async def test_call_timeout_is_terminal_and_persisted(tmp_path: Path) -> None:
    adapter = ControlledAdapter({"qwen35-4b:qg_01_requirement_coverage": 0.05})
    summary = await run_benchmark(
        request(tmp_path, call_timeout_seconds=0.01),
        RunnerDependencies(clients, adapter),
    )
    result = summary.results[0]
    assert result.status == "timeout"
    assert result.timeout_stage == "call"
    assert (tmp_path / summary.run_id / "progress.json").is_file()


@pytest.mark.asyncio
async def test_model_timeout_does_not_stall_later_model(tmp_path: Path) -> None:
    adapter = ControlledAdapter(
        {
            "qwen35-4b:qg_01_requirement_coverage": 0.006,
            "qwen35-4b:ma_01_supported_star": 0.006,
        }
    )
    summary = await run_benchmark(
        request(
            tmp_path,
            model_ids=("qwen35-4b", "qwen35-9b"),
            call_timeout_seconds=0.008,
            model_timeout_seconds=0.01,
        ),
        RunnerDependencies(clients, adapter),
    )
    assert any(item.attempt.model_id == "qwen35-9b" for item in summary.results)
    assert summary.state == "incomplete_deadline"


@pytest.mark.asyncio
async def test_whole_run_deadline_flushes_partial_progress(tmp_path: Path) -> None:
    adapter = ControlledAdapter(
        {
            "qwen35-4b:qg_01_requirement_coverage": 0.006,
            "qwen35-4b:ma_01_supported_star": 0.006,
        }
    )
    summary = await run_benchmark(
        request(
            tmp_path,
            call_timeout_seconds=0.008,
            model_timeout_seconds=0.01,
            run_timeout_seconds=0.01,
        ),
        RunnerDependencies(clients, adapter),
    )
    assert summary.state == "incomplete_deadline"
    assert any(item.timeout_stage == "whole_run" for item in summary.results)
    assert (tmp_path / summary.run_id / "summary.json").is_file()


@pytest.mark.asyncio
async def test_timeout_overrides_must_be_ordered_and_bounded(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="call <= model <= run"):
        await run_benchmark(
            request(
                tmp_path,
                call_timeout_seconds=2,
                model_timeout_seconds=1,
            ),
            RunnerDependencies(clients, ControlledAdapter()),
        )


@pytest.mark.asyncio
async def test_interruption_flushes_incomplete_summary_and_reraises(tmp_path: Path) -> None:
    class InterruptingAdapter(ControlledAdapter):
        async def execute(self, scenario, client, context):
            del scenario, client, context
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await run_benchmark(
            request(tmp_path),
            RunnerDependencies(clients, InterruptingAdapter()),
        )
    summaries = list(tmp_path.glob("*/summary.json"))
    assert len(summaries) == 1
    assert '"state": "incomplete_interrupted"' in summaries[0].read_text()


@pytest.mark.asyncio
async def test_protected_state_mutation_invalidates_harness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hashes = iter(
        [
            {"profile": "before", "database": "before"},
            {"profile": "after", "database": "before"},
        ]
    )
    monkeypatch.setattr(coach_runner, "_protected_hashes", lambda: next(hashes))
    summary = await run_benchmark(
        request(tmp_path),
        RunnerDependencies(clients, ControlledAdapter()),
    )
    assert summary.state == "invalid_harness_integrity"
