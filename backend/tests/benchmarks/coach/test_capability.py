from __future__ import annotations

from copy import deepcopy

from benchmarks.coach.contracts import (
    DimensionResult,
    GateFinding,
    ScenarioResult,
    ScheduleEntry,
)
from benchmarks.coach.scoring import classify_model


def _result(
    stage: str,
    index: int,
    *,
    status: str = "completed",
    scope: str = "model_capability",
    scenario_id: str | None = None,
    quality: str = "90.0",
    gates: list[GateFinding] | None = None,
    repair_count: int = 0,
) -> ScenarioResult:
    scenario_id = scenario_id or f"{stage}-{index}"
    return ScenarioResult(
        attempt=ScheduleEntry(
            attempt_id=f"model-a--{scenario_id}--{index}",
            model_id="model-a",
            scenario_id=scenario_id,
            stage=stage,
            qualification_scope=scope,
            repetition=1 if index % 2 else 2,
            seed=11 if index % 2 else 23,
        ),
        status=status,
        stage_outcome=(
            "withheld_insufficient_evidence"
            if status == "withheld_insufficient_evidence"
            else status
        ),
        duration_ms=10,
        repair_count=repair_count,
        gates=gates or [],
        dimensions=(
            {
                "dimension_band_agreement": DimensionResult(
                    score="100.0", weight="0.35", applicable=True
                )
            }
            if stage == "answer_evaluation"
            else {}
        ),
        quality_score=quality,
        calibration_in_range=6 if stage == "answer_evaluation" else None,
        calibration_applicable=6 if stage == "answer_evaluation" else None,
        calibration_error="0.0" if stage == "answer_evaluation" else None,
    )


def passing_results() -> list[ScenarioResult]:
    results = []
    for stage, count in (
        ("question_generation", 4),
        ("model_answer", 4),
        ("answer_evaluation", 10),
        ("session_report", 2),
        ("company_research", 4),
        ("rubric_synthesis", 4),
        ("technical_drill", 4),
    ):
        for index in range(1, count + 1):
            scenario_id = (
                "sr_01_mixed_session_report" if stage == "session_report" else None
            )
            results.append(_result(stage, index, scenario_id=scenario_id))
    results.extend(
        _result(
            "session_report",
            index,
            status="fallback",
            scope="harness_contract",
            scenario_id="sr_02_provider_fallback",
        )
        for index in (1, 2)
    )
    return results


def test_passing_minimums_classify_coach_capable() -> None:
    capability = classify_model("model-a", passing_results(), "completed")
    assert capability.classification == "coach_capable"
    assert capability.metrics["core_structured_success_rate"].numerator == 20
    assert capability.metrics["core_structured_success_rate"].denominator == 20


def test_insufficient_answer_evaluation_evidence_is_inconclusive() -> None:
    results = [
        item
        for item in passing_results()
        if item.attempt.stage != "answer_evaluation"
    ]
    results.extend(_result("answer_evaluation", index) for index in range(1, 8))
    assert classify_model("model-a", results, "completed").classification == "inconclusive"


def test_harness_attempts_never_enter_model_denominators() -> None:
    results = passing_results()
    results.append(
        _result(
            "answer_evaluation",
            99,
            status="unavailable",
            scope="harness_contract",
            scenario_id="ae_h01_provider_unavailable",
        )
    )
    metric = classify_model("model-a", results, "completed").metrics[
        "core_structured_success_rate"
    ]
    assert (metric.numerator, metric.denominator) == (20, 20)


def test_exact_nineteen_of_twenty_structured_success_passes_threshold() -> None:
    results = passing_results()
    target = next(item for item in results if item.attempt.stage == "answer_evaluation")
    target.status = "invalid"
    target.stage_outcome = "invalid_output"
    capability = classify_model("model-a", results, "completed_with_model_outcomes")
    assert capability.classification == "coach_capable"


def test_exact_hard_gate_band_mae_and_timeout_boundaries_pass() -> None:
    results = passing_results()
    evaluations = [
        item for item in results if item.attempt.stage == "answer_evaluation"
    ]
    for index, item in enumerate(evaluations):
        item.calibration_in_range = 5 if index < 8 else 4
        item.calibration_error = "1.5"
    timeout = next(item for item in results if item.attempt.stage == "model_answer")
    timeout.status = "timeout"
    timeout.stage_outcome = "unavailable"
    non_safety = [
        item for item in results if item.attempt.stage == "question_generation"
    ][:2]
    for item in non_safety:
        item.gates = [GateFinding(code="coach_question_duplicate", blocking=True)]
    capability = classify_model("model-a", results, "completed_with_model_outcomes")
    assert capability.classification == "coach_capable"
    assert capability.metrics["timeout_unavailable_rate"].display == "5.0"


def test_report_fidelity_failure_is_not_capable() -> None:
    results = passing_results()
    report = next(
        item
        for item in results
        if item.attempt.scenario_id == "sr_01_mixed_session_report"
    )
    report.gates = [GateFinding(code="coach_report_count_mismatch", blocking=True)]
    capability = classify_model("model-a", results, "completed_with_model_outcomes")
    assert capability.classification == "not_coach_capable"


def test_optional_failure_causes_only_optional_degradation() -> None:
    results = passing_results()
    target = next(item for item in results if item.attempt.stage == "technical_drill")
    target.status = "unavailable"
    target.stage_outcome = "unavailable"
    capability = classify_model("model-a", results, "completed_with_model_outcomes")
    assert capability.classification == "coach_capable_with_optional_degradation"
    assert capability.degraded_stages == ["technical_drill"]


def test_safety_gate_causes_not_capable_with_sufficient_evidence() -> None:
    results = passing_results()
    target = next(item for item in results if item.attempt.stage == "model_answer")
    target.gates = [
        GateFinding(code="coach_model_answer_numeric_fidelity", blocking=True)
    ]
    assert classify_model("model-a", results, "completed").classification == "not_coach_capable"


def test_expected_withholding_and_non_safety_repair_count_as_success() -> None:
    results = passing_results()
    model_answer = next(item for item in results if item.attempt.stage == "model_answer")
    model_answer.status = "withheld_insufficient_evidence"
    model_answer.stage_outcome = "withheld_insufficient_evidence"
    question = next(item for item in results if item.attempt.stage == "question_generation")
    question.repair_count = 1
    capability = classify_model("model-a", results, "completed")
    assert capability.metrics["core_structured_success_rate"].numerator == 20
    assert capability.ranking_metrics["question_generation_repair_rate"] == "0.25"


def test_optional_judge_cannot_change_classification() -> None:
    baseline = passing_results()
    judged = deepcopy(baseline)
    for item in judged:
        item.optional_judge_score = "0.0"
    assert classify_model("model-a", baseline, "completed").classification == classify_model(
        "model-a", judged, "completed"
    ).classification
