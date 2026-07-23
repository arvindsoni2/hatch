from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from app.services.coach_contracts import CoachDiagnostic
from benchmarks.coach.production_adapter import StageExecution
from benchmarks.coach.runner import (
    RunRequest,
    RunnerDependencies,
    resume_benchmark,
    run_benchmark,
)

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
async def test_resume_skips_terminal_attempts(tmp_path: Path) -> None:
    first_adapter = ControlledAdapter()
    summary = await run_benchmark(
        request(tmp_path), RunnerDependencies(clients, first_adapter)
    )
    resumed_adapter = ControlledAdapter()
    resumed = await resume_benchmark(
        tmp_path / summary.run_id,
        dependencies=RunnerDependencies(clients, resumed_adapter),
    )
    assert resumed.terminal == summary.terminal
    assert resumed_adapter.calls == []


@pytest.mark.asyncio
async def test_timeout_retries_only_with_explicit_flag(tmp_path: Path) -> None:
    first = ControlledAdapter({"qwen35-4b:qg_01_requirement_coverage": 0.05})
    summary = await run_benchmark(
        request(tmp_path, call_timeout_seconds=0.01),
        RunnerDependencies(clients, first),
    )
    no_retry = ControlledAdapter()
    await resume_benchmark(
        tmp_path / summary.run_id,
        dependencies=RunnerDependencies(clients, no_retry),
    )
    assert no_retry.calls == []
    retry = ControlledAdapter()
    await resume_benchmark(
        tmp_path / summary.run_id,
        retry_timeouts=True,
        dependencies=RunnerDependencies(clients, retry),
    )
    assert retry.calls[0][1] == "qg_01_requirement_coverage"


@pytest.mark.asyncio
async def test_resume_rejects_run_identity_mismatch(tmp_path: Path) -> None:
    summary = await run_benchmark(
        request(tmp_path), RunnerDependencies(clients, ControlledAdapter())
    )
    manifest = tmp_path / summary.run_id / "run_manifest.json"
    value = manifest.read_text()
    manifest.write_text(value.replace('"identity": "', '"identity": "changed-'))
    with pytest.raises(ValueError, match="run identity mismatch"):
        await resume_benchmark(
            tmp_path / summary.run_id,
            dependencies=RunnerDependencies(clients, ControlledAdapter()),
        )


@pytest.mark.asyncio
async def test_resume_rejects_modified_timeout_configuration(tmp_path: Path) -> None:
    summary = await run_benchmark(
        request(tmp_path), RunnerDependencies(clients, ControlledAdapter())
    )
    manifest = tmp_path / summary.run_id / "run_manifest.json"
    value = json.loads(manifest.read_text())
    value["request"]["call_timeout_seconds"] = 0.02
    manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="run identity mismatch"):
        await resume_benchmark(
            tmp_path / summary.run_id,
            dependencies=RunnerDependencies(clients, ControlledAdapter()),
        )
