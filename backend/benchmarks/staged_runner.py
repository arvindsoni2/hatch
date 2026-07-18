"""Resumable staged coordinator for representative local-model selection."""
from __future__ import annotations

import hashlib
import json
import statistics
import subprocess
import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .case_loader import suite_case
from .contracts import BenchmarkSuite, RepetitionResult
from .runner import _protected_hashes, benchmark_profile, run_benchmark
from .selection import (
    ModelSelectionMetrics,
    SelectionDecision,
    StageQualification,
    decide_stage_c,
    qualify_stage_a,
    qualify_stage_b,
    rank_models,
)


class StrictStagedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaseExecution(StrictStagedModel):
    results: list[RepetitionResult]
    complete: bool


class StageProjection(StrictStagedModel):
    stage: str
    model_ids: list[str]
    case_ids: list[str]
    seeds: list[int]
    pair_count: int = Field(ge=0)
    projected_duration_seconds: float = Field(ge=0.0)


class StagedRunResult(StrictStagedModel):
    run_id: str
    state: Literal[
        "completed",
        "awaiting_restart_evidence",
        "incomplete_interrupted",
        "protected_state_changed",
    ]
    projections: list[StageProjection]
    stage_a_qualifications: list[StageQualification]
    stage_b_qualifications: list[StageQualification] = Field(default_factory=list)
    stage_b_model_ids: list[str] = Field(default_factory=list)
    challenger_model_id: str | None = None
    decision: SelectionDecision


class RestartEndpoint(StrictStagedModel):
    model_id: str
    healthy: bool


class RestartEvidence(StrictStagedModel):
    timestamp: datetime
    source_commit: str
    endpoints: list[RestartEndpoint] = Field(min_length=2)

    @field_validator("timestamp")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("restart evidence timestamp must include a timezone")
        return value


class ProtectedStateChangedError(RuntimeError):
    """Raised when benchmark execution mutates the profile or database."""


CaseExecutor = Callable[
    [object, list[str], int, Path, str, bool],
    Awaitable[CaseExecution],
]
ProtectedHashReader = Callable[[], dict[str, str]]
Emitter = Callable[[str], None]


def _require_recorded_protected_hashes(hashes: dict[str, str]) -> None:
    unavailable = {
        name
        for name in ("profile", "database")
        if hashes.get(name) in {None, "", "not_recorded"}
    }
    if unavailable:
        raise ProtectedStateChangedError(
            "protected database/profile hashes must be recorded before a staged run"
        )


def source_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


async def _default_executor(
    case: object,
    model_ids: list[str],
    repetitions: int,
    output_root: Path,
    run_id: str,
    resume: bool,
) -> CaseExecution:
    summary = await run_benchmark(
        case,  # type: ignore[arg-type]
        model_ids=model_ids,
        repetitions=repetitions,
        output_root=output_root,
        profile=benchmark_profile("extended"),
        run_id=None if resume else run_id,
        resume_run_id=run_id if resume else None,
        retry_timeouts=resume,
    )
    results: list[RepetitionResult] = []
    for model_id in model_ids:
        for repetition in range(1, repetitions + 1):
            path = (
                output_root
                / run_id
                / "runs"
                / model_id
                / f"{repetition:02d}"
                / "result.json"
            )
            if path.exists():
                results.append(
                    RepetitionResult.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                )
    return CaseExecution(
        results=results,
        complete=summary.completion_state
        not in {"incomplete_deadline", "incomplete_interrupted"},
    )


def selection_metrics(
    model_id: str,
    results: Sequence[RepetitionResult],
) -> ModelSelectionMetrics:
    selected = [item for item in results if item.model_id == model_id]
    pair_metrics = [
        item.pair_metrics for item in selected if item.pair_metrics is not None
    ]
    eligible_metrics = [
        item
        for item in pair_metrics
        if item.post_repair_hard_gate_passed
    ]
    qualities = [
        item.normalized_combined_quality
        for item in eligible_metrics
        if item.normalized_combined_quality is not None
    ]
    latencies = [
        item.eligible_pair_latency_ms
        for item in eligible_metrics
        if item.eligible_pair_latency_ms is not None
    ]
    memory = [
        item.peak_memory_mb
        for item in pair_metrics
        if item.peak_memory_mb is not None
    ]
    role_values: dict[str, list[float]] = {}
    cv_scores: list[float] = []
    cover_letter_scores: list[float] = []
    for item in selected:
        if not item.score or not item.score.eligible:
            continue
        if item.score.cv is not None:
            cv_scores.append(item.score.cv.total)
        if item.score.cover_letter is not None:
            cover_letter_scores.append(item.score.cover_letter.total)
        for document_name in ("cv", "cover_letter"):
            document = getattr(item.score, document_name)
            if document is None:
                continue
            for dimension_name, dimension in document.dimensions.items():
                key = f"{document_name}.{dimension_name}"
                role_values.setdefault(key, []).append(dimension.score)
    schema_successes = sum(
        item.status == "succeeded"
        and item.pair_metrics is not None
        and item.pair_metrics.schema_succeeded
        for item in selected
    )
    infrastructure_failures = sum(
        item.status in {"unavailable", "timeout", "interrupted", "failed"}
        for item in selected
    )
    sparse_metrics = [
        item for item in pair_metrics if item.missing_evidence_case
    ]
    repairs = [
        item.cover_letter_repair_count
        for item in selected
        if item.status == "succeeded"
    ]
    first_pass_latencies = [
        item.first_pass_latency_ms
        for item in pair_metrics
        if item.first_pass_latency_ms is not None
    ]
    repair_latencies = [
        item.repair_latency_ms
        for item in pair_metrics
        if item.repair_latency_ms is not None
    ]
    output_tokens = [
        item.output_tokens
        for item in pair_metrics
        if item.output_tokens is not None
    ]
    eligible_tokens = [
        item.tokens_per_eligible_pair
        for item in eligible_metrics
        if item.tokens_per_eligible_pair is not None
    ]
    return ModelSelectionMetrics(
        model_id=model_id,
        attempted=len(selected),
        successful_responses=sum(item.status == "succeeded" for item in selected),
        schema_successes=schema_successes,
        first_pass_hard_gate_passes=sum(
            item.first_pass_hard_gate_passed for item in pair_metrics
        ),
        post_repair_hard_gate_passes=sum(
            item.post_repair_hard_gate_passed for item in pair_metrics
        ),
        eligible_pairs=len(eligible_metrics),
        unsupported_candidate_claims=sum(
            item.unsupported_candidate_claims for item in eligible_metrics
        ),
        unsupported_numeric_tokens=sum(
            item.unsupported_numeric_tokens for item in eligible_metrics
        ),
        immutable_token_mutations=sum(
            item.immutable_token_mutations for item in pair_metrics
        ),
        infrastructure_failures=infrastructure_failures,
        median_normalized_combined_quality=(
            statistics.median(qualities) if qualities else None
        ),
        normalized_combined_quality_variance=(
            statistics.pvariance(qualities) if qualities else None
        ),
        median_eligible_pair_latency_ms=(
            statistics.median(latencies) if latencies else None
        ),
        peak_memory_mb=max(memory) if memory else None,
        role_specific_median_scores={
            key: statistics.median(values)
            for key, values in role_values.items()
        },
        median_cv_quality=statistics.median(cv_scores) if cv_scores else None,
        median_cover_letter_quality=(
            statistics.median(cover_letter_scores)
            if cover_letter_scores
            else None
        ),
        mean_repair_count=statistics.mean(repairs) if repairs else 0.0,
        median_repair_count=statistics.median(repairs) if repairs else 0.0,
        missing_evidence_safe_fallback_rate=(
            sum(item.missing_evidence_safe_fallback for item in sparse_metrics)
            / len(sparse_metrics)
            if sparse_metrics
            else None
        ),
        mean_evidence_coverage=(
            statistics.mean(item.evidence_coverage for item in pair_metrics)
            if pair_metrics
            else 0.0
        ),
        median_first_pass_latency_ms=(
            statistics.median(first_pass_latencies)
            if first_pass_latencies
            else None
        ),
        median_repair_latency_ms=(
            statistics.median(repair_latencies) if repair_latencies else None
        ),
        median_output_tokens=(
            statistics.median(output_tokens) if output_tokens else None
        ),
        median_tokens_per_eligible_pair=(
            statistics.median(eligible_tokens) if eligible_tokens else None
        ),
    )


def stage_metrics_from_progress(
    run_dir: Path,
) -> dict[str, list[ModelSelectionMetrics]]:
    """Rebuild privacy-safe stage aggregates from ignored pair artifacts."""
    payload = json.loads(
        (run_dir / "staged_progress.json").read_text(encoding="utf-8")
    )
    grouped_results: dict[str, list[RepetitionResult]] = {
        "A": [],
        "B": [],
        "C1": [],
        "C2": [],
    }
    prefixes = {
        "stage-a": "A",
        "stage-b": "B",
        "stage-c-1": "C1",
        "stage-c-2": "C2",
    }
    for unit_id, raw_results in payload.get("unit_results", {}).items():
        stage = next(
            (
                stage_name
                for prefix, stage_name in prefixes.items()
                if unit_id.startswith(prefix + "--")
            ),
            None,
        )
        if stage is None:
            continue
        grouped_results[stage].extend(
            RepetitionResult.model_validate(item) for item in raw_results
        )
    return {
        stage: [
            selection_metrics(model_id, results)
            for model_id in sorted({item.model_id for item in results})
        ]
        for stage, results in grouped_results.items()
        if results
    }


def _projection(
    stage: str,
    model_ids: list[str],
    case_ids: list[str],
    seeds: list[int],
    latency_seconds: dict[str, float],
) -> StageProjection:
    repetitions = len(seeds)
    pair_count = len(model_ids) * len(case_ids) * repetitions
    projected = sum(
        latency_seconds[model_id] * len(case_ids) * repetitions
        for model_id in model_ids
    )
    return StageProjection(
        stage=stage,
        model_ids=model_ids,
        case_ids=case_ids,
        seeds=seeds,
        pair_count=pair_count,
        projected_duration_seconds=projected,
    )


def _print_projection(projection: StageProjection, emit: Emitter) -> None:
    emit(
        f"Stage {projection.stage} projection: {projection.pair_count} pairs, "
        f"{projection.projected_duration_seconds / 60:.1f} minutes"
    )


def _select_stage_b_models(
    metrics: list[ModelSelectionMetrics],
    qualifications: list[StageQualification],
    baseline_model_id: str,
) -> list[str]:
    advancing = {item.model_id for item in qualifications if item.advances}
    ranked_ids = [
        item.model_id for item in rank_models(metrics) if item.model_id in advancing
    ]
    challengers = [
        model_id for model_id in ranked_ids if model_id != baseline_model_id
    ][:2]
    return [baseline_model_id, *challengers]


def _latency_estimates(
    model_ids: Sequence[str],
    metrics: Sequence[ModelSelectionMetrics],
    fallback: dict[str, float],
) -> dict[str, float]:
    by_model = {item.model_id: item for item in metrics}
    return {
        model_id: (
            by_model[model_id].median_eligible_pair_latency_ms / 1000
            if model_id in by_model
            and by_model[model_id].median_eligible_pair_latency_ms is not None
            else fallback[model_id]
        )
        for model_id in model_ids
    }


def _evidence_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_restart_evidence(
    path: Path,
    *,
    required_models: set[str],
    not_before: datetime,
    used_hashes: set[str],
    expected_source_commit: str,
) -> tuple[RestartEvidence, str]:
    digest = _evidence_hash(path)
    if digest in used_hashes:
        raise ValueError("restart evidence cannot be reused")
    evidence = RestartEvidence.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    if evidence.source_commit != expected_source_commit:
        raise ValueError("restart evidence source commit does not match the staged run")
    if evidence.timestamp <= not_before:
        raise ValueError("restart evidence must be newer than the preceding stage boundary")
    healthy_models = {
        endpoint.model_id for endpoint in evidence.endpoints if endpoint.healthy
    }
    if not required_models <= healthy_models:
        raise ValueError("restart evidence must show both Stage C models healthy")
    return evidence, digest


def _pending_decision(
    baseline_model_id: str,
    challenger_model_id: str | None,
    rationale: str,
) -> SelectionDecision:
    return SelectionDecision(
        decision="benchmark_deferred",
        baseline_model_id=baseline_model_id,
        challenger_model_id=challenger_model_id,
        rationale=[rationale],
    )


async def run_stage_suite(
    suite: BenchmarkSuite,
    *,
    output_root: Path,
    run_id: str | None = None,
    resume_run_id: str | None = None,
    defer_stage_c: bool = False,
    restart_evidence: Sequence[Path] = (),
    executor: CaseExecutor = _default_executor,
    emit: Emitter = print,
    protected_hash_reader: ProtectedHashReader = _protected_hashes,
) -> StagedRunResult:
    if run_id and resume_run_id:
        raise ValueError("run_id and resume_run_id are mutually exclusive")
    staged_run_id = (
        resume_run_id
        or run_id
        or f"staged-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    )
    run_dir = output_root / staged_run_id
    progress_path = run_dir / "staged_progress.json"
    manifest_path = run_dir / "staged_manifest.json"
    if resume_run_id:
        if not progress_path.exists():
            raise ValueError(f"cannot resume unknown staged run: {resume_run_id}")
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        if progress["suite_hash"] != suite.suite_hash:
            raise ValueError("cannot resume with a different benchmark suite")
        if source_commit() != progress["source_commit"]:
            raise ValueError("cannot resume after the benchmark source commit changed")
        protected_before = progress["protected_hashes_before"]
        if protected_hash_reader() != protected_before:
            progress["state"] = "protected_state_changed"
            _atomic_write(progress_path, progress)
            raise ProtectedStateChangedError(
                "protected database/profile hashes changed since the staged run began"
            )
    else:
        protected_before = protected_hash_reader()
        _require_recorded_protected_hashes(protected_before)
        progress = {
            "run_id": staged_run_id,
            "suite_hash": suite.suite_hash,
            "source_commit": source_commit(),
            "state": "running",
            "protected_hashes_before": protected_before,
            "completed_units": [],
            "started_units": [],
            "unit_results": {},
            "projections": [],
            "used_restart_evidence_hashes": [],
            "restart_evidence": [],
            "official_run_metrics": [],
            "restart_not_before": datetime.now(UTC).isoformat(),
        }
        _atomic_write(
            manifest_path,
            {
                "run_id": staged_run_id,
                "suite_id": suite.suite_id,
                "suite_hash": suite.suite_hash,
                "source_commit": progress["source_commit"],
                "baseline_model_id": suite.baseline_model_id,
                "stage_plan": {
                    "A": {"pairs": 15},
                    "B": {"maximum_pairs": 36},
                    "C": {"pairs_per_official_run": 80, "official_runs": 2},
                },
            },
        )
        _atomic_write(progress_path, progress)

    completed_units = set(progress["completed_units"])
    started_units = set(progress["started_units"])
    unit_results = {
        unit_id: [
            RepetitionResult.model_validate(item)
            for item in payloads
        ]
        for unit_id, payloads in progress["unit_results"].items()
    }
    projections = [
        StageProjection.model_validate(item) for item in progress["projections"]
    ]

    def persist(state: str = "running") -> None:
        progress["state"] = state
        progress["completed_units"] = sorted(completed_units)
        progress["started_units"] = sorted(started_units)
        progress["unit_results"] = {
            unit_id: [
                item.model_dump(mode="json") for item in results
            ]
            for unit_id, results in unit_results.items()
        }
        progress["projections"] = [
            item.model_dump(mode="json") for item in projections
        ]
        _atomic_write(progress_path, progress)

    def ensure_protected() -> None:
        if protected_hash_reader() != protected_before:
            persist("protected_state_changed")
            raise ProtectedStateChangedError(
                "benchmark changed protected database/profile state"
            )

    def add_projection(projection: StageProjection) -> None:
        if not any(item.stage == projection.stage for item in projections):
            projections.append(projection)
            persist()
        _print_projection(projection, emit)

    async def execute_units(
        *,
        stage_prefix: str,
        case_ids: Sequence[str],
        model_ids: list[str],
        repetitions: int,
    ) -> bool:
        for case_id in case_ids:
            unit_id = f"{stage_prefix}--{case_id}"
            if unit_id in completed_units:
                continue
            resume = unit_id in started_units
            started_units.add(unit_id)
            persist()
            execution = await executor(
                suite_case(suite, case_id),
                model_ids,
                repetitions,
                run_dir / "pair-runs",
                unit_id,
                resume,
            )
            unit_results[unit_id] = execution.results
            if not execution.complete:
                persist("incomplete_interrupted")
                return False
            completed_units.add(unit_id)
            persist()
            ensure_protected()
        return True

    stage_a_case_ids = ["delivery-project-manager"]
    stage_a_models = [model.id for model in suite.models]
    stage_a_projection = _projection(
        "A",
        stage_a_models,
        stage_a_case_ids,
        suite.seeds[:3],
        suite.historical_median_pair_seconds,
    )
    add_projection(stage_a_projection)
    if not await execute_units(
        stage_prefix="stage-a",
        case_ids=stage_a_case_ids,
        model_ids=stage_a_models,
        repetitions=3,
    ):
        return StagedRunResult(
            run_id=staged_run_id,
            state="incomplete_interrupted",
            projections=projections,
            stage_a_qualifications=[],
            decision=_pending_decision(
                suite.baseline_model_id,
                None,
                "Stage A is incomplete and must be resumed.",
            ),
        )
    stage_a_results = [
        item
        for unit_id, results in unit_results.items()
        if unit_id.startswith("stage-a")
        for item in results
    ]
    stage_a_metrics = [
        selection_metrics(model_id, stage_a_results)
        for model_id in stage_a_models
    ]
    stage_a_qualifications = [
        qualify_stage_a(item, baseline_model_id=suite.baseline_model_id)
        for item in stage_a_metrics
    ]
    stage_b_models = _select_stage_b_models(
        stage_a_metrics,
        stage_a_qualifications,
        suite.baseline_model_id,
    )
    progress["stage_b_model_ids"] = stage_b_models

    stage_b_projection = _projection(
        "B",
        stage_b_models,
        suite.stage_b_case_ids,
        suite.seeds[:3],
        _latency_estimates(
            stage_b_models,
            stage_a_metrics,
            suite.historical_median_pair_seconds,
        ),
    )
    add_projection(stage_b_projection)
    if not await execute_units(
        stage_prefix="stage-b",
        case_ids=suite.stage_b_case_ids,
        model_ids=stage_b_models,
        repetitions=3,
    ):
        return StagedRunResult(
            run_id=staged_run_id,
            state="incomplete_interrupted",
            projections=projections,
            stage_a_qualifications=stage_a_qualifications,
            stage_b_model_ids=stage_b_models,
            decision=_pending_decision(
                suite.baseline_model_id,
                None,
                "Stage B is incomplete and must be resumed.",
            ),
        )
    stage_b_results = [
        item
        for unit_id, results in unit_results.items()
        if unit_id.startswith("stage-b")
        for item in results
    ]
    stage_b_metrics = [
        selection_metrics(model_id, stage_b_results)
        for model_id in stage_b_models
    ]
    stage_b_qualifications = [
        qualify_stage_b(item, baseline_model_id=suite.baseline_model_id)
        for item in stage_b_metrics
    ]
    qualifying_challenger_ids = {
        item.model_id
        for item in stage_b_qualifications
        if item.qualified and item.model_id != suite.baseline_model_id
    }
    challenger = next(
        (
            item.model_id
            for item in rank_models(stage_b_metrics)
            if item.model_id in qualifying_challenger_ids
        ),
        None,
    )
    progress["challenger_model_id"] = challenger
    if challenger is None:
        decision = SelectionDecision(
            decision="retain_baseline",
            baseline_model_id=suite.baseline_model_id,
            rationale=["No non-baseline model qualified in Stage B."],
        )
        progress["decision"] = decision.model_dump(mode="json")
        persist("completed")
        ensure_protected()
        _atomic_write(run_dir / "selection.json", decision.model_dump(mode="json"))
        return StagedRunResult(
            run_id=staged_run_id,
            state="completed",
            projections=projections,
            stage_a_qualifications=stage_a_qualifications,
            stage_b_qualifications=stage_b_qualifications,
            stage_b_model_ids=stage_b_models,
            decision=decision,
        )

    stage_c_models = [suite.baseline_model_id, challenger]
    c_latency = _latency_estimates(
        stage_c_models,
        stage_b_metrics,
        suite.historical_median_pair_seconds,
    )
    for run_number in (1, 2):
        add_projection(
            _projection(
                f"C{run_number}",
                stage_c_models,
                [case.case_id for case in suite.cases],
                suite.seeds[:5],
                c_latency,
            )
        )

    if defer_stage_c:
        decision = _pending_decision(
            suite.baseline_model_id,
            challenger,
            "The operator deferred Stage C; this run cannot authorize a model change.",
        )
        progress["decision"] = decision.model_dump(mode="json")
        persist("completed")
        ensure_protected()
        _atomic_write(run_dir / "selection.json", decision.model_dump(mode="json"))
        return StagedRunResult(
            run_id=staged_run_id,
            state="completed",
            projections=projections,
            stage_a_qualifications=stage_a_qualifications,
            stage_b_qualifications=stage_b_qualifications,
            stage_b_model_ids=stage_b_models,
            challenger_model_id=challenger,
            decision=decision,
        )

    evidence_paths = list(restart_evidence)
    official_metrics = [
        (
            ModelSelectionMetrics.model_validate(item["challenger"]),
            ModelSelectionMetrics.model_validate(item["baseline"]),
        )
        for item in progress.get("official_run_metrics", [])
    ]
    used_hashes = set(progress["used_restart_evidence_hashes"])
    for run_number in range(len(official_metrics) + 1, 3):
        if not evidence_paths:
            progress["restart_not_before"] = datetime.now(UTC).isoformat()
            decision = _pending_decision(
                suite.baseline_model_id,
                challenger,
                f"Stage C official run {run_number} requires fresh restart evidence.",
            )
            progress["decision"] = decision.model_dump(mode="json")
            persist("awaiting_restart_evidence")
            return StagedRunResult(
                run_id=staged_run_id,
                state="awaiting_restart_evidence",
                projections=projections,
                stage_a_qualifications=stage_a_qualifications,
                stage_b_qualifications=stage_b_qualifications,
                stage_b_model_ids=stage_b_models,
                challenger_model_id=challenger,
                decision=decision,
            )
        evidence_path = evidence_paths.pop(0)
        _, digest = _validate_restart_evidence(
            evidence_path,
            required_models=set(stage_c_models),
            not_before=datetime.fromisoformat(progress["restart_not_before"]),
            used_hashes=used_hashes,
            expected_source_commit=progress["source_commit"],
        )
        validated_evidence = RestartEvidence.model_validate_json(
            evidence_path.read_text(encoding="utf-8")
        )
        used_hashes.add(digest)
        progress["used_restart_evidence_hashes"] = sorted(used_hashes)
        progress["restart_evidence"].append(
            {
                "sha256": digest,
                **validated_evidence.model_dump(mode="json"),
            }
        )
        persist()
        stage_prefix = f"stage-c-{run_number}"
        if not await execute_units(
            stage_prefix=stage_prefix,
            case_ids=[case.case_id for case in suite.cases],
            model_ids=stage_c_models,
            repetitions=5,
        ):
            return StagedRunResult(
                run_id=staged_run_id,
                state="incomplete_interrupted",
                projections=projections,
                stage_a_qualifications=stage_a_qualifications,
                stage_b_qualifications=stage_b_qualifications,
                stage_b_model_ids=stage_b_models,
                challenger_model_id=challenger,
                decision=_pending_decision(
                    suite.baseline_model_id,
                    challenger,
                    f"Stage C official run {run_number} is incomplete.",
                ),
            )
        official_results = [
            item
            for unit_id, results in unit_results.items()
            if unit_id.startswith(stage_prefix)
            for item in results
        ]
        pair = (
            selection_metrics(challenger, official_results),
            selection_metrics(suite.baseline_model_id, official_results),
        )
        official_metrics.append(pair)
        progress["official_run_metrics"] = [
            {
                "challenger": challenger_metrics.model_dump(mode="json"),
                "baseline": baseline_metrics.model_dump(mode="json"),
            }
            for challenger_metrics, baseline_metrics in official_metrics
        ]
        progress["restart_not_before"] = datetime.now(UTC).isoformat()
        persist()
        if run_number == 1 and not evidence_paths:
            decision = _pending_decision(
                suite.baseline_model_id,
                challenger,
                "Stage C official run 2 requires a second fresh restart record.",
            )
            progress["decision"] = decision.model_dump(mode="json")
            persist("awaiting_restart_evidence")
            return StagedRunResult(
                run_id=staged_run_id,
                state="awaiting_restart_evidence",
                projections=projections,
                stage_a_qualifications=stage_a_qualifications,
                stage_b_qualifications=stage_b_qualifications,
                stage_b_model_ids=stage_b_models,
                challenger_model_id=challenger,
                decision=decision,
            )

    decision = decide_stage_c(
        official_metrics,
        baseline_model_id=suite.baseline_model_id,
        challenger_model_id=challenger,
    )
    progress["decision"] = decision.model_dump(mode="json")
    persist("completed")
    ensure_protected()
    _atomic_write(run_dir / "selection.json", decision.model_dump(mode="json"))
    return StagedRunResult(
        run_id=staged_run_id,
        state="completed",
        projections=projections,
        stage_a_qualifications=stage_a_qualifications,
        stage_b_qualifications=stage_b_qualifications,
        stage_b_model_ids=stage_b_models,
        challenger_model_id=challenger,
        decision=decision,
    )
