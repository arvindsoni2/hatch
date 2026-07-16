from __future__ import annotations

from benchmarks.contracts import (
    BenchmarkSummary,
    ModelAggregate,
    Recommendation,
)
from benchmarks.reporting import render_report


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
    )
    alternative = ModelAggregate(
        model_id="gemma4-e2b",
        attempted=3,
        succeeded=2,
        failed=1,
        unavailable=0,
        eligible=1,
        hard_gate_pass_rate=1 / 3,
        median_cv_score=90.0,
        median_cover_letter_score=92.5,
        median_writing_score=91.0,
        writing_score_variance=0.0,
        median_latency_ms=900.0,
        gate_codes={"unsupported_numeric_token": 1},
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
    assert "## Writing quality" in report
    assert "Median CV" in report
    assert "Median cover letter" in report
    assert "## Operational metrics" in report
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
