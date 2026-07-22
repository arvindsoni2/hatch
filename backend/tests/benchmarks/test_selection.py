from __future__ import annotations

import pytest

from benchmarks.selection import (
    ModelSelectionMetrics,
    decide_stage_c,
    qualify_stage_a,
    qualify_stage_b,
    rank_models,
)


BASELINE = "qwen35-4b"
CHALLENGER = "qwen35-9b"


def metrics(
    model_id: str,
    *,
    attempted: int = 40,
    responses: int = 40,
    schema: int = 40,
    first: int = 40,
    post: int = 40,
    eligible: int | None = None,
    claims: int = 0,
    numeric: int = 0,
    mutations: int = 0,
    quality: float | None = 90.0,
    variance: float | None = 1.0,
    latency: float | None = 750.0,
    memory: float | None = 800.0,
    role_scores: dict[str, float] | None = None,
    infrastructure_failures: int = 0,
) -> ModelSelectionMetrics:
    return ModelSelectionMetrics(
        model_id=model_id,
        attempted=attempted,
        successful_responses=responses,
        schema_successes=schema,
        first_pass_hard_gate_passes=first,
        post_repair_hard_gate_passes=post,
        eligible_pairs=post if eligible is None else eligible,
        unsupported_candidate_claims=claims,
        unsupported_numeric_tokens=numeric,
        immutable_token_mutations=mutations,
        median_normalized_combined_quality=quality,
        normalized_combined_quality_variance=variance,
        median_eligible_pair_latency_ms=latency,
        peak_memory_mb=memory,
        role_specific_median_scores=role_scores or {"grounding": 90.0},
        infrastructure_failures=infrastructure_failures,
    )


def test_stage_a_passes_at_two_of_three_and_fails_at_one() -> None:
    passing = qualify_stage_a(
        metrics(CHALLENGER, attempted=3, responses=3, schema=3, first=2, post=2),
        baseline_model_id=BASELINE,
    )
    failing = qualify_stage_a(
        metrics(CHALLENGER, attempted=3, responses=3, schema=3, first=1, post=1),
        baseline_model_id=BASELINE,
    )

    assert passing.qualified is True
    assert passing.advances is True
    assert failing.qualified is False
    assert failing.advances is False


def test_stage_a_baseline_advances_but_retains_failure_evidence() -> None:
    result = qualify_stage_a(
        metrics(BASELINE, attempted=3, responses=3, schema=3, first=1, post=1),
        baseline_model_id=BASELINE,
    )

    assert result.qualified is False
    assert result.advances is True
    assert result.baseline_override is True
    assert any(
        threshold.name == "post_repair_hard_gate_passes"
        and threshold.passed is False
        for threshold in result.thresholds
    )


def test_stage_a_rejects_numeric_and_infrastructure_failures() -> None:
    numeric = qualify_stage_a(
        metrics(
            CHALLENGER,
            attempted=3,
            responses=3,
            schema=3,
            first=3,
            post=3,
            numeric=1,
        ),
        baseline_model_id=BASELINE,
    )
    infrastructure = qualify_stage_a(
        metrics(
            CHALLENGER,
            attempted=3,
            responses=2,
            schema=2,
            first=2,
            post=2,
            infrastructure_failures=1,
        ),
        baseline_model_id=BASELINE,
    )

    assert numeric.advances is False
    assert infrastructure.advances is False


def test_stage_b_exact_boundaries_pass() -> None:
    result = qualify_stage_b(
        metrics(
            CHALLENGER,
            attempted=12,
            responses=12,
            schema=11,
            first=9,
            post=11,
        ),
        baseline_model_id=BASELINE,
    )

    assert result.qualified is True
    assert result.advances is True
    assert all(threshold.passed for threshold in result.thresholds)


def test_stage_b_each_locked_threshold_can_fail() -> None:
    variants = [
        {"post": 10},
        {"first": 8},
        {"claims": 1},
        {"mutations": 1},
        {"schema": 10},
    ]

    for variant in variants:
        result = qualify_stage_b(
            metrics(
                CHALLENGER,
                attempted=12,
                responses=12,
                schema=variant.get("schema", 11),
                first=variant.get("first", 9),
                post=variant.get("post", 11),
                claims=variant.get("claims", 0),
                mutations=variant.get("mutations", 0),
            ),
            baseline_model_id=BASELINE,
        )
        assert result.qualified is False


def test_stage_qualifications_require_complete_expected_pair_counts() -> None:
    stage_a = qualify_stage_a(
        metrics(CHALLENGER, attempted=2, responses=2, schema=2, first=2, post=2),
        baseline_model_id=BASELINE,
    )
    stage_b = qualify_stage_b(
        metrics(
            CHALLENGER,
            attempted=11,
            responses=11,
            schema=11,
            first=9,
            post=11,
        ),
        baseline_model_id=BASELINE,
    )

    assert stage_a.qualified is False
    assert stage_b.qualified is False


def test_ranking_is_lexicographic_and_zero_eligible_is_last() -> None:
    faster_but_ineligible = metrics(
        "ineligible",
        attempted=3,
        responses=3,
        schema=3,
        first=0,
        post=0,
        eligible=0,
        quality=None,
        variance=None,
        latency=1.0,
    )
    higher_first_pass = metrics(
        "higher-first",
        attempted=3,
        responses=3,
        schema=3,
        first=3,
        post=2,
        quality=80.0,
        latency=900.0,
    )
    higher_quality = metrics(
        "higher-quality",
        attempted=3,
        responses=3,
        schema=3,
        first=2,
        post=2,
        quality=99.0,
        latency=100.0,
    )

    ranked = rank_models(
        [faster_but_ineligible, higher_quality, higher_first_pass]
    )

    assert [item.model_id for item in ranked] == [
        "higher-first",
        "higher-quality",
        "ineligible",
    ]


def test_stage_c_exact_latency_boundaries_change_default() -> None:
    baseline = metrics(
        BASELINE,
        quality=90.0,
        latency=1000.0,
        role_scores={"grounding": 90.0, "coverage": 88.0},
    )
    challenger = metrics(
        CHALLENGER,
        responses=39,
        post=38,
        quality=87.0,
        latency=750.0,
        role_scores={"grounding": 85.0, "coverage": 83.0},
    )

    decision = decide_stage_c(
        [(challenger, baseline), (challenger, baseline)],
        baseline_model_id=BASELINE,
        challenger_model_id=CHALLENGER,
    )

    assert decision.decision == "change_default"
    assert len(decision.official_runs) == 2
    assert all(run.passed for run in decision.official_runs)


def test_stage_c_exact_memory_boundary_passes_with_ten_percent_slower_latency() -> None:
    baseline = metrics(BASELINE, latency=1000.0, memory=1000.0)
    challenger = metrics(
        CHALLENGER,
        responses=39,
        post=38,
        quality=87.0,
        latency=1100.0,
        memory=800.0,
        role_scores={"grounding": 85.0},
    )

    decision = decide_stage_c(
        [(challenger, baseline), (challenger, baseline)],
        baseline_model_id=BASELINE,
        challenger_model_id=CHALLENGER,
    )

    assert decision.decision == "change_default"


@pytest.mark.parametrize(
    ("challenger_overrides", "failed_threshold"),
    [
        ({"post": 37}, "post_repair_hard_gate_passes"),
        ({"claims": 1}, "unsupported_candidate_claims"),
        ({"mutations": 1}, "immutable_token_mutations"),
        ({"quality": 86.999}, "median_quality_delta"),
        (
            {"role_scores": {"grounding": 84.999}},
            "worst_role_specific_median_delta",
        ),
        ({"latency": 750.001}, "meaningful_operational_improvement"),
        ({"responses": 38}, "successful_responses"),
        ({"attempted": 39}, "requested_pairs"),
    ],
)
def test_stage_c_rejects_values_just_below_each_boundary(
    challenger_overrides: dict[str, object],
    failed_threshold: str,
) -> None:
    baseline = metrics(BASELINE, latency=1000.0, memory=None)
    values: dict[str, object] = {
        "responses": 39,
        "post": 38,
        "quality": 87.0,
        "latency": 750.0,
        "memory": None,
        "role_scores": {"grounding": 85.0},
    }
    values.update(challenger_overrides)
    challenger = metrics(CHALLENGER, **values)  # type: ignore[arg-type]

    decision = decide_stage_c(
        [(challenger, baseline), (challenger, baseline)],
        baseline_model_id=BASELINE,
        challenger_model_id=CHALLENGER,
    )

    assert decision.decision == "retain_baseline"
    assert any(
        threshold.name == failed_threshold and threshold.passed is False
        for threshold in decision.official_runs[0].thresholds
    )


def test_stage_c_memory_path_rejects_more_than_ten_percent_slower_latency() -> None:
    baseline = metrics(BASELINE, latency=1000.0, memory=1000.0)
    challenger = metrics(
        CHALLENGER,
        responses=39,
        post=38,
        quality=87.0,
        latency=1100.001,
        memory=800.0,
        role_scores={"grounding": 85.0},
    )

    decision = decide_stage_c(
        [(challenger, baseline), (challenger, baseline)],
        baseline_model_id=BASELINE,
        challenger_model_id=CHALLENGER,
    )

    assert decision.decision == "retain_baseline"


def test_stage_c_requires_same_passing_decision_in_both_runs() -> None:
    baseline = metrics(BASELINE, latency=1000.0)
    passing = metrics(CHALLENGER, responses=39, post=38, latency=750.0)
    failing = metrics(CHALLENGER, responses=38, post=38, latency=750.0)

    decision = decide_stage_c(
        [(passing, baseline), (failing, baseline)],
        baseline_model_id=BASELINE,
        challenger_model_id=CHALLENGER,
    )

    assert decision.decision == "retain_baseline"
    assert [run.passed for run in decision.official_runs] == [True, False]


def test_missing_or_deferred_stage_c_is_benchmark_deferred() -> None:
    baseline = metrics(BASELINE, latency=1000.0)
    challenger = metrics(CHALLENGER, responses=39, post=38, latency=750.0)

    missing = decide_stage_c(
        [(challenger, baseline)],
        baseline_model_id=BASELINE,
        challenger_model_id=CHALLENGER,
    )
    deferred = decide_stage_c(
        [(challenger, baseline), (challenger, baseline)],
        baseline_model_id=BASELINE,
        challenger_model_id=CHALLENGER,
        deferred=True,
    )

    assert missing.decision == "benchmark_deferred"
    assert deferred.decision == "benchmark_deferred"
