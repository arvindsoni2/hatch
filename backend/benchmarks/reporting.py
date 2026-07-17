"""Stable Markdown rendering for benchmark summaries."""
from __future__ import annotations

from pathlib import Path

from .contracts import BenchmarkSummary, ModelAggregate


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
