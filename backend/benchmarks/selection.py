"""Pure staged qualification and locked model-selection decisions."""
from __future__ import annotations

import math
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field


class StrictSelectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelSelectionMetrics(StrictSelectionModel):
    """Aggregate inputs used by ranking and stage threshold evaluation."""

    model_id: str = Field(min_length=1)
    attempted: int = Field(ge=0)
    successful_responses: int = Field(ge=0)
    schema_successes: int = Field(ge=0)
    first_pass_hard_gate_passes: int = Field(ge=0)
    post_repair_hard_gate_passes: int = Field(ge=0)
    eligible_pairs: int = Field(ge=0)
    unsupported_candidate_claims: int = Field(default=0, ge=0)
    unsupported_numeric_tokens: int = Field(default=0, ge=0)
    immutable_token_mutations: int = Field(default=0, ge=0)
    infrastructure_failures: int = Field(default=0, ge=0)
    median_normalized_combined_quality: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
    )
    normalized_combined_quality_variance: float | None = Field(
        default=None,
        ge=0.0,
    )
    median_eligible_pair_latency_ms: float | None = Field(default=None, ge=0.0)
    peak_memory_mb: float | None = Field(default=None, ge=0.0)
    role_specific_median_scores: dict[str, float] = Field(default_factory=dict)
    median_cv_quality: float | None = Field(default=None, ge=0.0, le=100.0)
    median_cover_letter_quality: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
    )
    mean_repair_count: float = Field(default=0.0, ge=0.0)
    median_repair_count: float = Field(default=0.0, ge=0.0)
    missing_evidence_safe_fallback_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    mean_evidence_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    median_first_pass_latency_ms: float | None = Field(default=None, ge=0.0)
    median_repair_latency_ms: float | None = Field(default=None, ge=0.0)
    median_output_tokens: float | None = Field(default=None, ge=0.0)
    median_tokens_per_eligible_pair: float | None = Field(default=None, ge=0.0)

    @property
    def post_repair_hard_gate_rate(self) -> float:
        return (
            self.post_repair_hard_gate_passes / self.attempted
            if self.attempted
            else 0.0
        )

    @property
    def first_pass_hard_gate_rate(self) -> float:
        return (
            self.first_pass_hard_gate_passes / self.attempted
            if self.attempted
            else 0.0
        )

    @property
    def successful_response_rate(self) -> float:
        return self.successful_responses / self.attempted if self.attempted else 0.0


class ThresholdResult(StrictSelectionModel):
    name: str
    passed: bool
    observed: float | int | bool | str | None
    required: str


class StageQualification(StrictSelectionModel):
    stage: Literal["A", "B"]
    model_id: str
    qualified: bool
    advances: bool
    baseline_override: bool = False
    thresholds: list[ThresholdResult]


class OfficialRunDecision(StrictSelectionModel):
    run_number: int = Field(ge=1)
    challenger_model_id: str
    baseline_model_id: str
    passed: bool
    thresholds: list[ThresholdResult]


class SelectionDecision(StrictSelectionModel):
    decision: Literal[
        "retain_baseline",
        "change_default",
        "benchmark_deferred",
    ]
    baseline_model_id: str
    challenger_model_id: str | None = None
    official_runs: list[OfficialRunDecision] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)


def _threshold(
    name: str,
    passed: bool,
    observed: float | int | bool | str | None,
    required: str,
) -> ThresholdResult:
    return ThresholdResult(
        name=name,
        passed=passed,
        observed=observed,
        required=required,
    )


def rank_models(
    models: Sequence[ModelSelectionMetrics],
) -> list[ModelSelectionMetrics]:
    """Rank eligible models using the specification's safety-first ordering."""

    def key(item: ModelSelectionMetrics) -> tuple[float | int | str, ...]:
        has_eligible_output = item.eligible_pairs > 0
        quality = item.median_normalized_combined_quality
        variance = item.normalized_combined_quality_variance
        latency = item.median_eligible_pair_latency_ms
        return (
            0 if has_eligible_output else 1,
            -item.post_repair_hard_gate_rate,
            -item.first_pass_hard_gate_rate,
            -(quality if quality is not None else -math.inf),
            variance if variance is not None else math.inf,
            latency if latency is not None else math.inf,
            item.model_id,
        )

    return sorted(models, key=key)


def qualify_stage_a(
    metrics: ModelSelectionMetrics,
    *,
    baseline_model_id: str,
) -> StageQualification:
    thresholds = [
        _threshold(
            "requested_pairs",
            metrics.attempted == 3,
            metrics.attempted,
            "exactly 3",
        ),
        _threshold(
            "post_repair_hard_gate_passes",
            metrics.post_repair_hard_gate_passes >= 2,
            metrics.post_repair_hard_gate_passes,
            ">= 2 of 3",
        ),
        _threshold(
            "unsupported_numeric_tokens",
            metrics.unsupported_numeric_tokens == 0,
            metrics.unsupported_numeric_tokens,
            "0 among eligible pairs",
        ),
        _threshold(
            "infrastructure_failures",
            metrics.infrastructure_failures == 0,
            metrics.infrastructure_failures,
            "0",
        ),
    ]
    qualified = all(item.passed for item in thresholds)
    baseline_override = metrics.model_id == baseline_model_id and not qualified
    return StageQualification(
        stage="A",
        model_id=metrics.model_id,
        qualified=qualified,
        advances=qualified or metrics.model_id == baseline_model_id,
        baseline_override=baseline_override,
        thresholds=thresholds,
    )


def qualify_stage_b(
    metrics: ModelSelectionMetrics,
    *,
    baseline_model_id: str,
) -> StageQualification:
    thresholds = [
        _threshold(
            "requested_pairs",
            metrics.attempted == 12,
            metrics.attempted,
            "exactly 12",
        ),
        _threshold(
            "post_repair_hard_gate_passes",
            metrics.post_repair_hard_gate_passes >= 11,
            metrics.post_repair_hard_gate_passes,
            ">= 11 of 12",
        ),
        _threshold(
            "first_pass_hard_gate_passes",
            metrics.first_pass_hard_gate_passes >= 9,
            metrics.first_pass_hard_gate_passes,
            ">= 9 of 12",
        ),
        _threshold(
            "unsupported_candidate_claims",
            metrics.unsupported_candidate_claims == 0,
            metrics.unsupported_candidate_claims,
            "0 among eligible pairs",
        ),
        _threshold(
            "immutable_token_mutations",
            metrics.immutable_token_mutations == 0,
            metrics.immutable_token_mutations,
            "0 after repair",
        ),
        _threshold(
            "schema_successes",
            metrics.schema_successes >= 11,
            metrics.schema_successes,
            ">= 11 of 12",
        ),
    ]
    qualified = all(item.passed for item in thresholds)
    baseline_override = metrics.model_id == baseline_model_id and not qualified
    return StageQualification(
        stage="B",
        model_id=metrics.model_id,
        qualified=qualified,
        advances=qualified or metrics.model_id == baseline_model_id,
        baseline_override=baseline_override,
        thresholds=thresholds,
    )


def _at_least(value: float, boundary: float) -> bool:
    return value > boundary or math.isclose(value, boundary, abs_tol=1e-12)


def _at_most(value: float, boundary: float) -> bool:
    return value < boundary or math.isclose(value, boundary, abs_tol=1e-12)


def _official_run_decision(
    challenger: ModelSelectionMetrics,
    baseline: ModelSelectionMetrics,
    *,
    run_number: int,
) -> OfficialRunDecision:
    quality_delta = (
        challenger.median_normalized_combined_quality
        - baseline.median_normalized_combined_quality
        if challenger.median_normalized_combined_quality is not None
        and baseline.median_normalized_combined_quality is not None
        else None
    )
    role_deltas = {
        role: challenger.role_specific_median_scores[role] - baseline_score
        for role, baseline_score in baseline.role_specific_median_scores.items()
        if role in challenger.role_specific_median_scores
    }
    roles_complete = (
        bool(baseline.role_specific_median_scores)
        and set(role_deltas) == set(baseline.role_specific_median_scores)
    )
    worst_role_delta = min(role_deltas.values()) if roles_complete else None

    baseline_latency = baseline.median_eligible_pair_latency_ms
    challenger_latency = challenger.median_eligible_pair_latency_ms
    latency_improvement = (
        (baseline_latency - challenger_latency) / baseline_latency
        if baseline_latency
        and challenger_latency is not None
        else None
    )
    baseline_memory = baseline.peak_memory_mb
    challenger_memory = challenger.peak_memory_mb
    memory_improvement = (
        (baseline_memory - challenger_memory) / baseline_memory
        if baseline_memory
        and challenger_memory is not None
        else None
    )
    latency_path = (
        latency_improvement is not None
        and _at_least(latency_improvement, 0.25)
    )
    memory_path = bool(
        memory_improvement is not None
        and _at_least(memory_improvement, 0.20)
        and baseline_latency is not None
        and challenger_latency is not None
        and _at_most(challenger_latency, baseline_latency * 1.10)
    )
    operational_observed = (
        f"latency_improvement={latency_improvement!r}; "
        f"memory_improvement={memory_improvement!r}"
    )

    thresholds = [
        _threshold(
            "requested_pairs",
            challenger.attempted == 40,
            challenger.attempted,
            "exactly 40",
        ),
        _threshold(
            "post_repair_hard_gate_passes",
            challenger.post_repair_hard_gate_passes >= 38,
            challenger.post_repair_hard_gate_passes,
            ">= 38 of 40",
        ),
        _threshold(
            "unsupported_candidate_claims",
            challenger.unsupported_candidate_claims == 0,
            challenger.unsupported_candidate_claims,
            "0 among eligible pairs",
        ),
        _threshold(
            "immutable_token_mutations",
            challenger.immutable_token_mutations == 0,
            challenger.immutable_token_mutations,
            "0 after repair",
        ),
        _threshold(
            "median_quality_delta",
            quality_delta is not None and _at_least(quality_delta, -3.0),
            quality_delta,
            ">= -3.0 normalized points versus baseline",
        ),
        _threshold(
            "worst_role_specific_median_delta",
            worst_role_delta is not None
            and _at_least(worst_role_delta, -5.0),
            worst_role_delta,
            ">= -5.0 normalized points versus baseline for every role subscore",
        ),
        _threshold(
            "meaningful_operational_improvement",
            latency_path or memory_path,
            operational_observed,
            "latency >=25% lower, or memory >=20% lower with latency <=10% slower",
        ),
        _threshold(
            "successful_responses",
            challenger.successful_responses >= 39,
            challenger.successful_responses,
            ">= 39 of 40",
        ),
    ]
    return OfficialRunDecision(
        run_number=run_number,
        challenger_model_id=challenger.model_id,
        baseline_model_id=baseline.model_id,
        passed=all(item.passed for item in thresholds),
        thresholds=thresholds,
    )


def decide_stage_c(
    official_runs: Sequence[
        tuple[ModelSelectionMetrics, ModelSelectionMetrics]
    ],
    *,
    baseline_model_id: str,
    challenger_model_id: str,
    deferred: bool = False,
) -> SelectionDecision:
    """Apply every locked threshold independently to both official runs."""
    evaluated = [
        _official_run_decision(
            challenger,
            baseline,
            run_number=index,
        )
        for index, (challenger, baseline) in enumerate(official_runs, start=1)
    ]
    if deferred or len(evaluated) != 2:
        return SelectionDecision(
            decision="benchmark_deferred",
            baseline_model_id=baseline_model_id,
            challenger_model_id=challenger_model_id,
            official_runs=evaluated,
            rationale=[
                "Two complete independent Stage C runs are required before a model change."
            ],
        )
    if all(run.passed for run in evaluated):
        return SelectionDecision(
            decision="change_default",
            baseline_model_id=baseline_model_id,
            challenger_model_id=challenger_model_id,
            official_runs=evaluated,
            rationale=[
                "The challenger met every locked threshold independently in both official runs."
            ],
        )
    return SelectionDecision(
        decision="retain_baseline",
        baseline_model_id=baseline_model_id,
        challenger_model_id=challenger_model_id,
        official_runs=evaluated,
        rationale=[
            "At least one official run failed a locked model-change threshold."
        ],
    )
