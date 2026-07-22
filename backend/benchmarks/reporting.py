"""Stable Markdown rendering for benchmark summaries."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

from .contracts import BenchmarkSummary, ModelAggregate
from .selection import ModelSelectionMetrics, ThresholdResult
from .staged_runner import StagedRunResult


def _number(value: float | None, digits: int = 2) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}"


def _gate_text(model: ModelAggregate) -> str:
    if not model.gate_codes:
        return "None"
    return ", ".join(f"{code} ({count})" for code, count in sorted(model.gate_codes.items()))


def render_report(summary: BenchmarkSummary) -> str:
    lines = [
        "# Local Writing Model Benchmark",
        "",
        f"- Run: `{summary.run_id}`",
        f"- Case: `{summary.case_id}`",
        f"- Created: {summary.created_at}",
        f"- Repetitions per model: {summary.repetitions}",
        "",
        "## Safety and reliability",
        "",
        "| Model | Succeeded | Failed | Unavailable | Timeout | Interrupted | Gate pass rate | Blocking gates |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for model in summary.models:
        lines.append(
            f"| {model.model_id} | {model.succeeded}/{model.attempted} | {model.failed} | "
            f"{model.unavailable} | {model.timeout} | {model.interrupted} | "
            f"{model.hard_gate_pass_rate:.1%} | {_gate_text(model)} |"
        )

    lines.extend(
        [
            "",
            "## Writing quality",
            "",
            "Only hard-gate-passing repetitions contribute to these medians.",
            "",
            "| Model | Median CV | Median cover letter | Median combined | Variance |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for model in summary.models:
        lines.append(
            f"| {model.model_id} | {_number(model.median_cv_score)} | "
            f"{_number(model.median_cover_letter_score)} | {_number(model.median_writing_score)} | "
            f"{_number(model.writing_score_variance, 3)} |"
        )

    lines.extend(
        [
            "",
            "## Operational metrics",
            "",
            "| Model | First-pass gate rate | Post-repair gate rate | Repairs | Final body words | Numeric fidelity failures | Median pair latency (ms) | Total latency (ms) | Successful runs |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for model in summary.models:
        lines.append(
            f"| {model.model_id} | {model.first_pass_gate_pass_rate:.1%} | "
            f"{model.post_repair_gate_pass_rate:.1%} | {model.total_repair_count} | "
            f"{_number(model.median_final_cover_letter_body_words, 1)} | "
            f"{model.numeric_fidelity_failures} | {_number(model.median_latency_ms, 1)} | "
            f"{_number(model.total_latency_ms, 1)} | "
            f"{model.succeeded}/{model.attempted} |"
        )

    lines.extend(
        [
            "",
            "## Ranking",
            "",
            "Ranking is lexicographic: gate pass rate, median writing score, variance, then latency.",
            "",
            "| Rank | Model | Gate pass rate | Median combined |",
            "|---:|---|---:|---:|",
        ]
    )
    for rank, model in enumerate(summary.ranking, start=1):
        lines.append(
            f"| {rank} | {model.model_id} | {model.hard_gate_pass_rate:.1%} | "
            f"{_number(model.median_writing_score)} |"
        )

    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            f"**{summary.recommendation.classification.replace('_', ' ').title()}**",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in summary.recommendation.rationale)
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in summary.recommendation.limitations)
    return "\n".join(lines) + "\n"


def write_report(summary: BenchmarkSummary, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(render_report(summary), encoding="utf-8")
    temporary.replace(path)


_SAFE_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


def _safe_label(value: str) -> str:
    return value if _SAFE_LABEL_RE.fullmatch(value) else "redacted"


def _ratio(numerator: int, denominator: int) -> str:
    return f"{numerator}/{denominator} ({numerator / denominator:.1%})" if denominator else "0/0 (N/A)"


def _optional_rate(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.1%}"


def _role_scores(metrics: ModelSelectionMetrics) -> str:
    if not metrics.role_specific_median_scores:
        return "N/A"
    return ", ".join(
        f"{_safe_label(name)}={score:.2f}"
        for name, score in sorted(metrics.role_specific_median_scores.items())
    )


def _threshold_rows(
    run_number: int,
    thresholds: Sequence[ThresholdResult],
) -> list[str]:
    rows: list[str] = []
    for threshold in thresholds:
        observed = str(threshold.observed).replace("|", "\\|")
        required = threshold.required.replace("|", "\\|")
        rows.append(
            f"| {run_number} | {_safe_label(threshold.name)} | "
            f"{'PASS' if threshold.passed else 'FAIL'} | {observed} | {required} |"
        )
    return rows


def render_staged_report(
    staged: StagedRunResult,
    stage_metrics: dict[str, list[ModelSelectionMetrics]],
    *,
    protected_hashes_unchanged: bool,
) -> str:
    """Render a privacy-safe staged decision report from aggregate evidence."""
    lines = [
        "# Representative Local Writing Model Benchmark",
        "",
        f"- Run: `{_safe_label(staged.run_id)}`",
        f"- State: `{staged.state}`",
        "",
        "## Reliability",
        "",
        "| Stage | Model | Responses | Schema success | First-pass gates | Post-repair gates | Infrastructure failures |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for stage in ("A", "B", "C1", "C2"):
        for metrics in stage_metrics.get(stage, []):
            lines.append(
                f"| {stage} | {_safe_label(metrics.model_id)} | "
                f"{_ratio(metrics.successful_responses, metrics.attempted)} | "
                f"{_ratio(metrics.schema_successes, metrics.attempted)} | "
                f"{_ratio(metrics.first_pass_hard_gate_passes, metrics.attempted)} | "
                f"{_ratio(metrics.post_repair_hard_gate_passes, metrics.attempted)} | "
                f"{metrics.infrastructure_failures} |"
            )

    lines.extend(
        [
            "",
            "## Safety and fidelity",
            "",
            "| Stage | Model | Unsupported claims | Unsupported numeric tokens | Immutable mutations | Missing-evidence safe fallback | Mean evidence coverage |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for stage in ("A", "B", "C1", "C2"):
        for metrics in stage_metrics.get(stage, []):
            lines.append(
                f"| {stage} | {_safe_label(metrics.model_id)} | "
                f"{metrics.unsupported_candidate_claims} | "
                f"{metrics.unsupported_numeric_tokens} | "
                f"{metrics.immutable_token_mutations} | "
                f"{_optional_rate(metrics.missing_evidence_safe_fallback_rate)} | "
                f"{metrics.mean_evidence_coverage:.1%} |"
            )

    lines.extend(
        [
            "",
            "## Quality",
            "",
            "Only post-repair hard-gate-passing pairs contribute to quality aggregates.",
            "",
            "| Stage | Model | Median CV | Median cover letter | Median normalized combined | Variance | Role-specific medians |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for stage in ("A", "B", "C1", "C2"):
        for metrics in stage_metrics.get(stage, []):
            lines.append(
                f"| {stage} | {_safe_label(metrics.model_id)} | "
                f"{_number(metrics.median_cv_quality)} | "
                f"{_number(metrics.median_cover_letter_quality)} | "
                f"{_number(metrics.median_normalized_combined_quality)} | "
                f"{_number(metrics.normalized_combined_quality_variance, 3)} | "
                f"{_role_scores(metrics)} |"
            )

    lines.extend(
        [
            "",
            "## Operations",
            "",
            "| Stage | Model | Mean repairs | Median repairs | First-pass latency ms | Repair latency ms | Eligible-pair latency ms | Output tokens | Tokens per eligible pair | Peak memory MB |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for stage in ("A", "B", "C1", "C2"):
        for metrics in stage_metrics.get(stage, []):
            lines.append(
                f"| {stage} | {_safe_label(metrics.model_id)} | "
                f"{metrics.mean_repair_count:.2f} | "
                f"{metrics.median_repair_count:.2f} | "
                f"{_number(metrics.median_first_pass_latency_ms, 1)} | "
                f"{_number(metrics.median_repair_latency_ms, 1)} | "
                f"{_number(metrics.median_eligible_pair_latency_ms, 1)} | "
                f"{_number(metrics.median_output_tokens, 1)} | "
                f"{_number(metrics.median_tokens_per_eligible_pair, 1)} | "
                f"{_number(metrics.peak_memory_mb, 1)} |"
            )
    lines.extend(["", "Projected workload:", ""])
    lines.extend(
        f"- Stage {projection.stage}: {projection.pair_count} pairs; "
        f"{projection.projected_duration_seconds / 60:.1f} minutes"
        for projection in staged.projections
    )

    lines.extend(
        [
            "",
            "## Stage qualification",
            "",
            "| Stage | Model | Qualified | Advances | Comparator override |",
            "|---|---|---|---|---|",
        ]
    )
    for qualification in [
        *staged.stage_a_qualifications,
        *staged.stage_b_qualifications,
    ]:
        lines.append(
            f"| {qualification.stage} | {_safe_label(qualification.model_id)} | "
            f"{'yes' if qualification.qualified else 'no'} | "
            f"{'yes' if qualification.advances else 'no'} | "
            f"{'yes' if qualification.baseline_override else 'no'} |"
        )

    lines.extend(
        [
            "",
            "## Locked threshold evaluation",
            "",
        ]
    )
    if staged.decision.official_runs:
        lines.extend(
            [
                "| Official run | Threshold | Result | Observed | Required |",
                "|---:|---|---|---|---|",
            ]
        )
        for official_run in staged.decision.official_runs:
            lines.extend(
                _threshold_rows(
                    official_run.run_number,
                    official_run.thresholds,
                )
            )
    else:
        lines.append(
            "Not evaluated because Stage C did not produce two complete official runs."
        )

    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"**{staged.decision.decision}**",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in staged.decision.rationale)
    lines.extend(
        [
            "",
            "## Privacy",
            "",
            "- This report contains aggregate counts, rates, scores, and controlled identifiers only.",
            "- Generated documents, source fixture prose, and raw model responses remain in ignored run artifacts.",
            f"- Protected database/profile hashes unchanged: {'yes' if protected_hashes_unchanged else 'no'}.",
            "",
            "## Limitations",
            "",
            "- Results apply only to the controlled representative suite and recorded local runtimes.",
            "- Missing operation measurements are shown as N/A and are not inferred.",
            "- A deferred or incomplete Stage C cannot authorize a model change.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_staged_report(
    staged: StagedRunResult,
    stage_metrics: dict[str, list[ModelSelectionMetrics]],
    path: Path,
    *,
    protected_hashes_unchanged: bool,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        render_staged_report(
            staged,
            stage_metrics,
            protected_hashes_unchanged=protected_hashes_unchanged,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)
