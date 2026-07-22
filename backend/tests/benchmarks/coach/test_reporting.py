from __future__ import annotations

from pathlib import Path

from benchmarks.coach.contracts import (
    CapabilityResult,
    CoachRunSummary,
    FractionMetric,
    GateFinding,
    ScenarioResult,
    ScheduleEntry,
)
from benchmarks.coach.reporting import render_report, write_report


def _result(
    attempt_id: str,
    *,
    stage: str = "model_answer",
    scope: str = "model_capability",
    status: str = "completed",
    exclusion: str | None = None,
    gates: list[GateFinding] | None = None,
) -> ScenarioResult:
    return ScenarioResult(
        attempt=ScheduleEntry(
            attempt_id=attempt_id,
            model_id="qwen35-4b",
            scenario_id="ma_01_supported_star",
            stage=stage,
            qualification_scope=scope,
            repetition=1,
            seed=17,
        ),
        status=status,
        stage_outcome="completed" if status == "completed" else status,
        duration_ms=12,
        gates=gates or [],
        quality_score="8.5" if status == "completed" else None,
        exclusion_reason=exclusion,
        output_excerpt={"authorization": "Bearer should-never-render"},
    )


def _summary(*, profile: str = "acceptance-smoke") -> CoachRunSummary:
    return CoachRunSummary(
        run_id="run-safe",
        suite_id="hatch-coach-v1",
        suite_version="1.0.0",
        profile=profile,
        state="completed_with_model_outcomes",
        scheduled=2,
        terminal=2,
        results=[
            _result("done"),
            _result(
                "excluded",
                status="unavailable",
                exclusion="provider unavailable",
                gates=[GateFinding(code="coach_stage_timeout", blocking=False)],
            ),
        ],
        protected_hashes_before={"profile": "a" * 64, "database": "b" * 64},
        protected_hashes_after={"profile": "a" * 64, "database": "b" * 64},
    )


def test_acceptance_report_has_evidence_but_cannot_recommend_model() -> None:
    report = render_report(_summary())

    assert "Terminal attempts: **2/2**" in report
    assert "model_answer" in report
    assert "1/2" in report
    assert "provider unavailable" in report
    assert "coach_stage_timeout" in report
    assert "Harness validity: **valid**" in report
    assert "recommended_model" not in report
    assert "model change" not in report.casefold()
    assert "## Ranking" not in report


def test_standard_report_emits_raw_fraction_display_and_ranking() -> None:
    summary = _summary(profile="standard").model_copy(
        update={
            "capabilities": [
                CapabilityResult(
                    model_id="qwen35-4b",
                    classification="coach_capable",
                    metrics={
                        "core_hard_gate_rate": FractionMetric(
                            numerator=19,
                            denominator=20,
                            exact="0.95",
                            display="95.0%",
                        )
                    },
                    ranking_metrics={"median_core_quality": "8.5"},
                    rank=1,
                )
            ],
            "ranking": ["qwen35-4b"],
        }
    )

    report = render_report(summary)

    assert "19/20" in report
    assert "0.95" in report
    assert "95.0%" in report
    assert "## Ranking" in report
    assert "qwen35-4b" in report
    assert "median_core_quality" in report
    assert "8.5" in report


def test_report_uses_relative_artifact_names_and_omits_private_payloads() -> None:
    report = render_report(_summary())

    for name in (
        "manifest.json",
        "run_manifest.json",
        "progress.json",
        "summary.json",
        "aggregate.json",
        "report.md",
        "scenarios/",
    ):
        assert name in report
    assert "Bearer should-never-render" not in report
    assert "authorization" not in report.casefold()
    assert str(Path.cwd()) not in report


def test_invalid_harness_report_has_no_classification_or_ranking() -> None:
    summary = _summary(profile="standard").model_copy(
        update={
            "state": "invalid_harness_privacy",
            "capabilities": [],
            "ranking": [],
            "diagnostics": ["bounded privacy finding"],
        }
    )

    report = render_report(summary)

    assert "Harness validity: **invalid**" in report
    assert "bounded privacy finding" in report
    assert "## Capability" not in report
    assert "## Ranking" not in report


def test_write_report_atomically_replaces_target(tmp_path: Path) -> None:
    target = tmp_path / "report.md"
    target.write_text("old", encoding="utf-8")

    write_report(_summary(), target)

    assert target.read_text(encoding="utf-8") == render_report(_summary())
    assert list(tmp_path.glob("*.tmp")) == []
