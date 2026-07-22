from __future__ import annotations

import time
from pathlib import Path

import pytest

from benchmarks.coach.runner import RunRequest, run_benchmark

ROOT = Path(__file__).resolve().parents[4]
SUITE_PATH = ROOT / "backend/benchmarks/coach/fixtures/v1"


@pytest.mark.asyncio
async def test_contract_smoke_exercises_every_scenario_without_live_models(
    tmp_path: Path,
) -> None:
    started = time.monotonic()
    summary = await run_benchmark(
        RunRequest(
            suite_path=SUITE_PATH,
            output_root=tmp_path,
            profile_name="contract-smoke",
            model_ids=("qwen35-4b",),
            command="pytest contract smoke",
        )
    )

    assert time.monotonic() - started < 90
    assert summary.terminal == summary.scheduled == 20
    assert {item.attempt.scenario_id for item in summary.results} == {
        path.stem for path in (SUITE_PATH / "scenarios").glob("*.json")
    }
    assert summary.state == "completed"
    assert summary.capabilities == []
    assert summary.ranking == []
    report = (tmp_path / summary.run_id / "report.md").read_text(encoding="utf-8")
    assert "## Ranking" not in report
    assert "recommend" not in report.casefold()


def test_contract_smoke_profile_is_hard_bounded_to_ninety_seconds() -> None:
    from benchmarks.coach.profiles import profile_for

    profile = profile_for("contract-smoke")
    assert profile.call_timeout_seconds == 90
    assert profile.model_timeout_seconds == 90
    assert profile.run_timeout_seconds == 90
