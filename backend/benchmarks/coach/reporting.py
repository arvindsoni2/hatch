"""Privacy-bounded Markdown reports for Coach benchmark evidence."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from .artifacts import atomic_write_text
from .contracts import CoachRunSummary, FractionMetric

_SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SAFE_HASH = re.compile(r"^[0-9a-f]{64}$")
_SECRET = re.compile(r"(?i)(?:bearer\s+\S+|sk-[A-Za-z0-9_-]+)")
_POSIX_PATH = re.compile(r"(?<![A-Za-z0-9.])/(?:[^\s|]+/)*[^\s|]*")
_WINDOWS_PATH = re.compile(r"(?i)\b[A-Z]:[\\/][^\s|]+")
_ARTIFACTS = (
    "manifest.json",
    "run_manifest.json",
    "progress.json",
    "summary.json",
    "aggregate.json",
    "report.md",
    "scenarios/",
)


def _label(value: str) -> str:
    return value if _SAFE_LABEL.fullmatch(value) else "redacted"


def _text(value: str) -> str:
    bounded = value.replace("\n", " ").replace("|", "\\|")[:200]
    bounded = _SECRET.sub("[redacted]", bounded)
    bounded = _WINDOWS_PATH.sub("[redacted-path]", bounded)
    return _POSIX_PATH.sub("[redacted-path]", bounded)


def _hash(value: str | None) -> str:
    if value == "not_recorded" or (value and _SAFE_HASH.fullmatch(value)):
        return value
    return "redacted"


def _fraction(metric: FractionMetric) -> str:
    if metric.denominator == 0:
        return "0/0; exact=N/A; display=N/A"
    return (
        f"{metric.numerator}/{metric.denominator}; exact={metric.exact}; "
        f"display={metric.display}"
    )


def _harness_validity(summary: CoachRunSummary) -> str:
    if summary.state.startswith("invalid_harness_"):
        return "invalid"
    if summary.state.startswith("incomplete_"):
        return "incomplete"
    return "valid"


def _stage_rows(summary: CoachRunSummary) -> list[str]:
    grouped = defaultdict(list)
    for result in summary.results:
        grouped[result.attempt.stage].append(result)
    rows: list[str] = []
    for stage in sorted(grouped):
        results = grouped[stage]
        model = sum(
            item.attempt.qualification_scope == "model_capability" for item in results
        )
        harness = len(results) - model
        successful = sum(
            item.status in {"completed", "withheld_insufficient_evidence"}
            for item in results
        )
        excluded = sum(item.exclusion_reason is not None for item in results)
        blocking = sum(
            finding.blocking for item in results for finding in item.gates
        )
        quality = [float(item.quality_score) for item in results if item.quality_score]
        quality_text = "N/A" if not quality else f"{median(quality):.1f}"
        rows.append(
            f"| {_label(stage)} | {len(results)} | {model} | {harness} | "
            f"{successful}/{len(results)} | {excluded} | {blocking} | {quality_text} |"
        )
    return rows


def render_report(summary: CoachRunSummary) -> str:
    """Render aggregate Coach evidence without raw prompts, outputs, or local paths."""
    lines = [
        "# Hatch Coach Model Quality Benchmark",
        "",
        f"- Run: `{_label(summary.run_id)}`",
        f"- Suite: `{_label(summary.suite_id)}` version `{_label(summary.suite_version)}`",
        f"- Profile: `{_label(summary.profile)}`",
        f"- Run state: `{_label(summary.state)}`",
        f"- Harness validity: **{_harness_validity(summary)}**",
        f"- Terminal attempts: **{summary.terminal}/{summary.scheduled}**",
        "",
        "## Protected state",
        "",
        "| Resource | Before | After | Match |",
        "|---|---|---|---|",
    ]
    resources = sorted(
        set(summary.protected_hashes_before) | set(summary.protected_hashes_after)
    )
    if resources:
        for resource in resources:
            before = _hash(summary.protected_hashes_before.get(resource))
            after = _hash(summary.protected_hashes_after.get(resource))
            lines.append(
                f"| {_label(resource)} | `{before}` | `{after}` | "
                f"{'yes' if before == after and before != 'redacted' else 'no'} |"
            )
    else:
        lines.append("| not_recorded | `not_recorded` | `not_recorded` | N/A |")

    lines.extend(
        [
            "",
            "## Stage metrics",
            "",
            "| Stage | Terminal | Model scope | Harness scope | Successful | Excluded | Blocking gates | Median quality |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
            *_stage_rows(summary),
        ]
    )
    if not summary.results:
        lines.append("| none | 0 | 0 | 0 | 0/0 | 0 | 0 | N/A |")

    gates = Counter(
        (finding.code, finding.blocking)
        for result in summary.results
        for finding in result.gates
    )
    lines.extend(["", "## Gate findings", ""])
    if gates:
        lines.extend(
            f"- `{_label(code)}` ({'blocking' if blocking else 'non-blocking'}): {count}"
            for (code, blocking), count in sorted(gates.items())
        )
    else:
        lines.append("- None")

    exclusions = [
        (result.attempt.attempt_id, result.exclusion_reason)
        for result in summary.results
        if result.exclusion_reason
    ]
    lines.extend(["", "## Exclusions", ""])
    if exclusions:
        lines.extend(
            f"- `{_label(attempt_id)}`: {_text(reason)}"
            for attempt_id, reason in exclusions
        )
    else:
        lines.append("- None")

    if summary.capabilities:
        lines.extend(
            [
                "",
                "## Capability classifications",
                "",
                "| Model | Classification | Rank | Degraded stages | Reasons |",
                "|---|---|---:|---|---|",
            ]
        )
        for capability in summary.capabilities:
            degraded = ", ".join(map(_label, capability.degraded_stages)) or "None"
            reasons = "; ".join(_text(item) for item in capability.reasons) or "None"
            lines.append(
                f"| {_label(capability.model_id)} | {_label(capability.classification)} | "
                f"{capability.rank or 'N/A'} | {degraded} | {reasons} |"
            )
        lines.extend(
            [
                "",
                "### Exact qualification metrics",
                "",
                "| Model | Metric | Raw fraction |",
                "|---|---|---|",
            ]
        )
        for capability in summary.capabilities:
            for name, metric in sorted(capability.metrics.items()):
                lines.append(
                    f"| {_label(capability.model_id)} | {_label(name)} | {_fraction(metric)} |"
                )
        lines.extend(
            [
                "",
                "### Ranking metrics",
                "",
                "| Model | Metric | Value |",
                "|---|---|---:|",
            ]
        )
        for capability in summary.capabilities:
            for name, value in sorted(capability.ranking_metrics.items()):
                lines.append(
                    f"| {_label(capability.model_id)} | {_label(name)} | {_text(value)} |"
                )

    if summary.ranking and summary.profile in {"standard", "extended"}:
        lines.extend(["", "## Ranking", ""])
        lines.extend(
            f"{rank}. `{_label(model_id)}`"
            for rank, model_id in enumerate(summary.ranking, start=1)
        )

    if summary.diagnostics:
        lines.extend(["", "## Harness diagnostics", ""])
        lines.extend(f"- {_text(item)}" for item in summary.diagnostics)

    lines.extend(["", "## Artifact paths", ""])
    lines.extend(f"- `{name}`" for name in _ARTIFACTS)
    lines.extend(
        [
            "",
            "This run is evidence for the configured synthetic suite, not a universal verdict on a model.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_report(summary: CoachRunSummary, path: Path) -> None:
    """Atomically write a regenerated Coach report."""
    atomic_write_text(path, render_report(summary))
