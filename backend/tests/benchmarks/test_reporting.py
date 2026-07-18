from __future__ import annotations

from benchmarks.contracts import (
    BenchmarkSummary,
    ModelAggregate,
    Recommendation,
)
from benchmarks.reporting import render_report, render_staged_report
from benchmarks.selection import (
    ModelSelectionMetrics,
    SelectionDecision,
    qualify_stage_a,
    qualify_stage_b,
)
from benchmarks.staged_runner import StageProjection, StagedRunResult


def test_report_contains_auditable_sections_and_ranking() -> None:
    baseline = ModelAggregate(
        model_id="qwen35-4b",
        attempted=3,
        succeeded=3,
        failed=0,
        unavailable=0,
        eligible=3,
        hard_gate_pass_rate=1.0,
        median_cv_score=87.0,
        median_cover_letter_score=90.75,
        median_writing_score=88.5,
        writing_score_variance=0.25,
        median_latency_ms=1200.0,
        first_pass_gate_pass_rate=2 / 3,
        post_repair_gate_pass_rate=1.0,
        total_repair_count=2,
        median_final_cover_letter_body_words=301.0,
        numeric_fidelity_failures=0,
        total_latency_ms=3600.0,
    )
    alternative = ModelAggregate(
        model_id="gemma4-e2b",
        attempted=3,
        succeeded=2,
        failed=1,
        unavailable=0,
        timeout=1,
        eligible=1,
        hard_gate_pass_rate=1 / 3,
        median_cv_score=90.0,
        median_cover_letter_score=92.5,
        median_writing_score=91.0,
        writing_score_variance=0.0,
        median_latency_ms=900.0,
        gate_codes={"unsupported_numeric_token": 1},
        first_pass_gate_pass_rate=1 / 3,
        post_repair_gate_pass_rate=1 / 3,
        total_repair_count=1,
        median_final_cover_letter_body_words=275.0,
        numeric_fidelity_failures=1,
        total_latency_ms=2700.0,
    )
    summary = BenchmarkSummary(
        run_id="run-1",
        case_id="delivery-manager",
        created_at="2026-07-15T12:00:00+00:00",
        repetitions=3,
        selected_models=["qwen35-4b", "gemma4-e2b"],
        models=[baseline, alternative],
        ranking=[baseline, alternative],
        recommendation=Recommendation(
            classification="keep_current_model",
            rationale=["Baseline ranks first."],
            limitations=["Single case."],
        ),
    )

    report = render_report(summary)

    assert "# Local Writing Model Benchmark" in report
    assert "## Safety and reliability" in report
    assert "Timeout" in report
    assert "Interrupted" in report
    assert "## Writing quality" in report
    assert "Median CV" in report
    assert "Median cover letter" in report
    assert "## Operational metrics" in report
    assert "First-pass gate rate" in report
    assert "Post-repair gate rate" in report
    assert "Repairs" in report
    assert "Final body words" in report
    assert "Numeric fidelity failures" in report
    assert "Total latency" in report
    assert "## Ranking" in report
    assert "## Recommendation" in report
    assert "## Limitations" in report
    assert "| 1 | qwen35-4b |" in report
    assert "unsupported_numeric_token" in report


def test_report_uses_na_for_missing_scores() -> None:
    unavailable = ModelAggregate(
        model_id="missing",
        attempted=3,
        succeeded=0,
        failed=0,
        unavailable=3,
        eligible=0,
        hard_gate_pass_rate=0.0,
    )
    summary = BenchmarkSummary(
        run_id="run-2",
        case_id="delivery-manager",
        created_at="2026-07-15T12:00:00+00:00",
        repetitions=3,
        selected_models=["missing"],
        models=[unavailable],
        ranking=[unavailable],
        recommendation=Recommendation(
            classification="inconclusive",
            rationale=["No eligible output."],
            limitations=["Single case."],
        ),
    )

    report = render_report(summary)

    assert "N/A" in report


def test_staged_report_is_complete_and_contains_only_aggregated_evidence() -> None:
    baseline = ModelSelectionMetrics(
        model_id="qwen35-4b",
        attempted=12,
        successful_responses=12,
        schema_successes=12,
        first_pass_hard_gate_passes=10,
        post_repair_hard_gate_passes=12,
        eligible_pairs=12,
        median_normalized_combined_quality=89.5,
        normalized_combined_quality_variance=1.25,
        median_eligible_pair_latency_ms=1200,
        role_specific_median_scores={"cv.grounding": 91.0},
        median_cv_quality=88.0,
        median_cover_letter_quality=91.0,
        mean_repair_count=0.25,
        median_repair_count=0.0,
        missing_evidence_safe_fallback_rate=1.0,
        mean_evidence_coverage=0.75,
        median_first_pass_latency_ms=1000,
        median_repair_latency_ms=200,
        median_output_tokens=850,
        median_tokens_per_eligible_pair=2500,
    )
    challenger = baseline.model_copy(
        update={
            "model_id": "qwen35-9b",
            "first_pass_hard_gate_passes": 9,
            "post_repair_hard_gate_passes": 11,
            "unsupported_candidate_claims": 0,
            "immutable_token_mutations": 0,
        }
    )
    staged = StagedRunResult(
        run_id="staged-20260717",
        state="completed",
        projections=[
            StageProjection(
                stage="A",
                model_ids=["qwen35-4b", "qwen35-9b"],
                case_ids=["delivery-project-manager"],
                seeds=[11, 23, 41],
                pair_count=6,
                projected_duration_seconds=120,
            )
        ],
        stage_a_qualifications=[
            qualify_stage_a(
                baseline.model_copy(
                    update={
                        "attempted": 3,
                        "successful_responses": 3,
                        "schema_successes": 3,
                        "first_pass_hard_gate_passes": 3,
                        "post_repair_hard_gate_passes": 3,
                        "eligible_pairs": 3,
                    }
                ),
                baseline_model_id="qwen35-4b",
            )
        ],
        stage_b_qualifications=[
            qualify_stage_b(challenger, baseline_model_id="qwen35-4b")
        ],
        stage_b_model_ids=["qwen35-4b", "qwen35-9b"],
        challenger_model_id="qwen35-9b",
        decision=SelectionDecision(
            decision="retain_baseline",
            baseline_model_id="qwen35-4b",
            challenger_model_id="qwen35-9b",
            rationale=["A locked threshold failed."],
        ),
    )

    report = render_staged_report(
        staged,
        {"B": [baseline, challenger]},
        protected_hashes_unchanged=True,
    )

    for heading in (
        "## Reliability",
        "## Safety and fidelity",
        "## Quality",
        "## Operations",
        "## Stage qualification",
        "## Locked threshold evaluation",
        "## Decision",
        "## Privacy",
        "## Limitations",
    ):
        assert heading in report
    assert "12/12" in report
    assert "Median CV" in report
    assert "Median cover letter" in report
    assert "89.50" in report
    assert "cv.grounding" in report
    assert "Protected database/profile hashes unchanged: yes" in report
    assert "/home/" not in report
    assert "body_paragraphs" not in report
    assert "master_cv" not in report
    assert "prompt" not in report.casefold()
