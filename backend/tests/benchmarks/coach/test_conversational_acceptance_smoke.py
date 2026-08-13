from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.coach.runner import RunRequest, run_benchmark
from benchmarks.coach.suite_loader import load_suite

ROOT = Path(__file__).resolve().parents[4]
CONVERSATIONAL_SUITE = ROOT / "backend/benchmarks/coach/fixtures/conversational_v1"


@pytest.mark.asyncio
async def test_conversational_acceptance_smoke_selects_one_case_per_group(
    tmp_path: Path,
) -> None:
    suite = load_suite(CONVERSATIONAL_SUITE)
    summary = await run_benchmark(
        RunRequest(
            suite_path=CONVERSATIONAL_SUITE,
            output_root=tmp_path,
            profile_name="acceptance-smoke",
            model_ids=("deterministic-contract",),
            command="pytest conversational acceptance smoke",
        )
    )

    expected = {
        item.scenario_id for item in suite.scenarios.values() if item.acceptance_smoke
    }
    assert {item.attempt.scenario_id for item in summary.results} == expected
    assert summary.terminal == summary.scheduled == 6
    assert summary.state == "completed"
    assert summary.ranking == []
    assert not [
        gate for result in summary.results for gate in result.gates if gate.blocking
    ]
