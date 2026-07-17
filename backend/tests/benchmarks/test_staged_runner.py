from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from benchmarks.case_loader import load_suite
from benchmarks.contracts import PairMetrics, PairScore, RepetitionResult
from benchmarks.staged_runner import (
    CaseExecution,
    ProtectedStateChangedError,
    run_stage_suite,
)


SUITE_PATH = (
    Path(__file__).resolve().parents[2]
    / "benchmarks"
    / "fixtures"
    / "representative_suite.json"
)


def result(
    model_id: str,
    repetition: int,
    seed: int,
    *,
    first: bool,
    post: bool,
) -> RepetitionResult:
    return RepetitionResult(
        model_id=model_id,
        repetition=repetition,
        seed=seed,
        status="succeeded",
        execution_status="completed",
        duration_ms=1000,
        score=PairScore(eligible=post, combined=90.0 if post else None),
        pair_metrics=PairMetrics(
            first_pass_hard_gate_passed=first,
            post_repair_hard_gate_passed=post,
            schema_succeeded=True,
            eligible_pair_latency_ms=1000 if post else None,
            normalized_combined_quality=90.0 if post else None,
        ),
        eligible_for_ranking=post,
    )


def executor(
    *,
    stage_b_challengers_pass: bool,
    calls: list[tuple[str, tuple[str, ...], int, bool]],
    interrupt_once: Callable[[str], bool] | None = None,
):
    async def execute(
        case,
        model_ids: list[str],
        repetitions: int,
        output_root: Path,
        run_id: str,
        resume: bool,
    ) -> CaseExecution:
        del output_root
        calls.append((run_id, tuple(model_ids), repetitions, resume))
        if interrupt_once and interrupt_once(run_id):
            return CaseExecution(results=[], complete=False)
        stage_b = run_id.startswith("stage-b")
        results = [
            result(
                model_id,
                repetition,
                case.seeds[repetition - 1],
                first=not stage_b or model_id == "qwen35-4b" or stage_b_challengers_pass,
                post=not stage_b or model_id == "qwen35-4b" or stage_b_challengers_pass,
            )
            for model_id in model_ids
            for repetition in range(1, repetitions + 1)
        ]
        return CaseExecution(results=results, complete=True)

    return execute


def write_restart_evidence(
    path: Path,
    *,
    timestamp: str,
    models: list[str],
) -> None:
    path.write_text(
        json.dumps(
            {
                "timestamp": timestamp,
                "source_commit": "source-commit",
                "endpoints": [
                    {"model_id": model_id, "healthy": True}
                    for model_id in models
                ],
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_stage_a_and_b_schedule_exact_bounded_pairs_and_stop_without_challenger(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, tuple[str, ...], int, bool]] = []
    lines: list[str] = []

    staged = await run_stage_suite(
        load_suite(SUITE_PATH),
        output_root=tmp_path,
        run_id="staged-no-challenger",
        executor=executor(
            stage_b_challengers_pass=False,
            calls=calls,
        ),
        emit=lines.append,
        protected_hash_reader=lambda: {"profile": "p", "database": "d"},
    )

    assert staged.decision.decision == "retain_baseline"
    assert staged.state == "completed"
    assert staged.projections[0].pair_count == 15
    assert staged.projections[1].pair_count <= 36
    assert len(staged.stage_b_model_ids) <= 3
    assert "qwen35-4b" in staged.stage_b_model_ids
    assert not any(call[0].startswith("stage-c") for call in calls)
    assert any("Stage A projection: 15 pairs" in line for line in lines)
    assert any("Stage B projection:" in line for line in lines)


@pytest.mark.asyncio
async def test_qualifying_challenger_requires_restart_evidence_or_can_be_deferred(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, tuple[str, ...], int, bool]] = []
    suite = load_suite(SUITE_PATH)

    waiting = await run_stage_suite(
        suite,
        output_root=tmp_path,
        run_id="staged-waiting",
        executor=executor(stage_b_challengers_pass=True, calls=calls),
        protected_hash_reader=lambda: {"profile": "p", "database": "d"},
    )
    deferred = await run_stage_suite(
        suite,
        output_root=tmp_path,
        run_id="staged-deferred",
        defer_stage_c=True,
        executor=executor(stage_b_challengers_pass=True, calls=[]),
        protected_hash_reader=lambda: {"profile": "p", "database": "d"},
    )

    assert waiting.state == "awaiting_restart_evidence"
    assert waiting.projections[-1].pair_count == 80
    assert waiting.decision.decision == "benchmark_deferred"
    assert deferred.state == "completed"
    assert deferred.decision.decision == "benchmark_deferred"


@pytest.mark.asyncio
async def test_two_fresh_restart_records_authorize_two_eighty_pair_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, tuple[str, ...], int, bool]] = []
    suite = load_suite(SUITE_PATH)
    monkeypatch.setattr(
        "benchmarks.staged_runner.source_commit",
        lambda: "source-commit",
    )
    waiting = await run_stage_suite(
        suite,
        output_root=tmp_path,
        run_id="staged-complete",
        executor=executor(stage_b_challengers_pass=True, calls=calls),
        protected_hash_reader=lambda: {"profile": "p", "database": "d"},
    )
    assert waiting.challenger_model_id is not None
    evidence_1 = tmp_path / "restart-1.json"
    evidence_2 = tmp_path / "restart-2.json"
    evidence_time = datetime.now(UTC) + timedelta(seconds=1)
    write_restart_evidence(
        evidence_1,
        timestamp=evidence_time.isoformat(),
        models=[suite.baseline_model_id, waiting.challenger_model_id],
    )
    after_first = await run_stage_suite(
        suite,
        output_root=tmp_path,
        resume_run_id="staged-complete",
        restart_evidence=[evidence_1],
        executor=executor(stage_b_challengers_pass=True, calls=calls),
        protected_hash_reader=lambda: {"profile": "p", "database": "d"},
    )
    assert after_first.state == "awaiting_restart_evidence"
    write_restart_evidence(
        evidence_2,
        timestamp=(evidence_time + timedelta(seconds=1)).isoformat(),
        models=[suite.baseline_model_id, waiting.challenger_model_id],
    )
    staged = await run_stage_suite(
        suite,
        output_root=tmp_path,
        resume_run_id="staged-complete",
        restart_evidence=[evidence_2],
        executor=executor(stage_b_challengers_pass=True, calls=calls),
        protected_hash_reader=lambda: {"profile": "p", "database": "d"},
    )

    stage_c_calls = [call for call in calls if call[0].startswith("stage-c")]
    assert len(stage_c_calls) == 16
    assert sum(len(models) * repetitions for _, models, repetitions, _ in stage_c_calls) == 160
    assert staged.state == "completed"
    assert staged.decision.decision in {"retain_baseline", "change_default"}


@pytest.mark.asyncio
async def test_resume_does_not_replay_completed_units(tmp_path: Path) -> None:
    calls: list[tuple[str, tuple[str, ...], int, bool]] = []
    interrupted = False

    def interrupt_once(run_id: str) -> bool:
        nonlocal interrupted
        if run_id.startswith("stage-b") and not interrupted:
            interrupted = True
            return True
        return False

    suite = load_suite(SUITE_PATH)
    first = await run_stage_suite(
        suite,
        output_root=tmp_path,
        run_id="staged-resume",
        executor=executor(
            stage_b_challengers_pass=False,
            calls=calls,
            interrupt_once=interrupt_once,
        ),
        protected_hash_reader=lambda: {"profile": "p", "database": "d"},
    )
    second = await run_stage_suite(
        suite,
        output_root=tmp_path,
        resume_run_id="staged-resume",
        executor=executor(
            stage_b_challengers_pass=False,
            calls=calls,
            interrupt_once=interrupt_once,
        ),
        protected_hash_reader=lambda: {"profile": "p", "database": "d"},
    )

    stage_a_calls = [call for call in calls if call[0].startswith("stage-a")]
    resumed_b_calls = [
        call for call in calls if call[0].startswith("stage-b") and call[3]
    ]
    assert first.state == "incomplete_interrupted"
    assert len(stage_a_calls) == 1
    assert resumed_b_calls
    assert second.state == "completed"


@pytest.mark.asyncio
async def test_protected_hash_change_aborts_staged_run(tmp_path: Path) -> None:
    reads = iter(
        [
            {"profile": "before", "database": "same"},
            {"profile": "after", "database": "same"},
        ]
    )

    with pytest.raises(ProtectedStateChangedError):
        await run_stage_suite(
            load_suite(SUITE_PATH),
            output_root=tmp_path,
            run_id="staged-protected-change",
            executor=executor(stage_b_challengers_pass=False, calls=[]),
            protected_hash_reader=lambda: next(reads),
        )

    progress = json.loads(
        (tmp_path / "staged-protected-change" / "staged_progress.json").read_text(
            encoding="utf-8"
        )
    )
    assert progress["state"] == "protected_state_changed"
