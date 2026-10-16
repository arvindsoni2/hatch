from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from benchmarks.coach.runner import RunRequest, run_benchmark

ROOT = Path(__file__).resolve().parents[4]
CONVERSATIONAL_SUITE = ROOT / "backend/benchmarks/coach/fixtures/conversational_v1"


@pytest.mark.asyncio
async def test_conversational_contract_smoke_exercises_every_scenario(
    tmp_path: Path,
) -> None:
    started = time.monotonic()
    summary = await run_benchmark(
        RunRequest(
            suite_path=CONVERSATIONAL_SUITE,
            output_root=tmp_path,
            profile_name="contract-smoke",
            model_ids=("deterministic-contract",),
            command="pytest conversational contract smoke",
        )
    )

    assert time.monotonic() - started < 90
    assert summary.terminal == summary.scheduled
    assert summary.scheduled == len(summary.results) > 6
    assert summary.state == "completed"
    assert not [
        gate for result in summary.results for gate in result.gates if gate.blocking
    ]
    assert {result.attempt.scenario_id for result in summary.results} == {
        path.stem for path in (CONVERSATIONAL_SUITE / "scenarios").glob("*.json")
    }


@pytest.mark.asyncio
async def test_conversational_artifacts_are_content_free(tmp_path: Path) -> None:
    summary = await run_benchmark(
        RunRequest(
            suite_path=CONVERSATIONAL_SUITE,
            output_root=tmp_path,
            profile_name="contract-smoke",
            model_ids=("deterministic-contract",),
            command="pytest conversational privacy smoke",
        )
    )

    serialized = json.dumps(summary.model_dump(mode="json"), sort_keys=True)
    assert "I led a safe migration" not in serialized
    assert "The transcript supports this named level." not in serialized
    assert "Project Apollo improved delivery" not in serialized
