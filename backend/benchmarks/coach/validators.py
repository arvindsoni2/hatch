"""Deterministic Coach stage contract gates applied after production validation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import CoachScenario
from .production_adapter import StageExecution

_NON_BLOCKING_GATES = {
    "coach_evaluation_followup_missing",
    "coach_evaluation_followup_unexpected",
    "coach_rubric_dimension_missing",
    "coach_rubric_optional_dimension_unexpected",
    "coach_report_priority_mismatch",
}
_EXPECTED_HARNESS_GATES = {
    "ae_h01_provider_unavailable": {"coach_evaluation_provider_unavailable"},
    "ae_h02_malformed_output": {"coach_evaluation_schema_invalid"},
    "sr_02_provider_fallback": {"coach_report_provider_unavailable"},
}
_QUESTION_CATEGORIES = {
    "Technical",
    "Behavioural",
    "Situational",
    "Domain",
    "Culture",
    "Commercial",
}
_EVALUATION_DIMENSIONS = {
    "relevance",
    "star_structure",
    "technical_depth",
    "conciseness",
    "communication",
    "impact_metrics",
}


@dataclass(frozen=True)
class ValidationFinding:
    code: str
    blocking: bool = True


@dataclass(frozen=True)
class ValidationResult:
    findings: tuple[ValidationFinding, ...] = ()

    @classmethod
    def from_codes(
        cls, codes: list[str], *, blocking: bool = True
    ) -> "ValidationResult":
        return cls(tuple(ValidationFinding(code, blocking) for code in codes))

    @property
    def blocking_codes(self) -> list[str]:
        return [item.code for item in self.findings if item.blocking]

    @property
    def eligible(self) -> bool:
        return not self.blocking_codes


def _add(findings: list[ValidationFinding], code: str, blocking: bool = True) -> None:
    if code not in {item.code for item in findings}:
        findings.append(ValidationFinding(code, blocking))


def _validate_question_generation(
    scenario: CoachScenario, output: dict[str, Any], findings: list[ValidationFinding]
) -> None:
    questions = output.get("questions")
    if not isinstance(questions, list):
        _add(findings, "coach_question_parse_invalid")
        return
    if len(questions) != scenario.input["question_count"]:
        _add(findings, "coach_question_count_mismatch")
    normalized: set[str] = set()
    for question in questions:
        if not isinstance(question, dict) or not isinstance(question.get("text"), str):
            _add(findings, "coach_question_parse_invalid")
            continue
        key = " ".join(question["text"].casefold().split())
        if key in normalized:
            _add(findings, "coach_question_duplicate")
        normalized.add(key)
        if question.get("category") not in _QUESTION_CATEGORIES:
            _add(findings, "coach_question_category_invalid")
        if question.get("difficulty") not in {"easy", "medium", "hard"}:
            _add(findings, "coach_question_difficulty_invalid")
        accepted = scenario.scoring.accepted_requirement_ids
        requirement_id = question.get("requirement_id")
        if accepted and requirement_id not in accepted:
            _add(findings, "coach_question_requirement_unknown")


def _validate_model_answer(
    scenario: CoachScenario,
    execution: StageExecution,
    output: dict[str, Any],
    findings: list[ValidationFinding],
) -> None:
    expected = scenario.expected.outcome
    actual = execution.diagnostic.outcome
    if expected == "withheld_insufficient_evidence":
        if actual != expected or output.get("model_answer") or output.get("evidence_references"):
            _add(findings, "coach_model_answer_no_evidence")
        return
    if actual != "completed" or not isinstance(output.get("model_answer"), str) or not output["model_answer"].strip():
        _add(findings, "coach_model_answer_empty")
    star = output.get("star_breakdown")
    if not isinstance(star, dict) or any(
        not isinstance(star.get(part), str) or not star[part].strip()
        for part in ("situation", "task", "action", "result")
    ):
        _add(findings, "coach_model_answer_star_incomplete")
    references = output.get("evidence_references")
    if not isinstance(references, list):
        _add(findings, "coach_model_answer_schema_invalid")
        return
    allowed = set(scenario.input.get("evidence_ids", []))
    if any(item not in allowed for item in references):
        _add(findings, "coach_model_answer_unknown_evidence_id")


def _validate_answer_evaluation(
    scenario: CoachScenario, output: dict[str, Any], findings: list[ValidationFinding]
) -> None:
    state = output.get("evaluation_state")
    expected = scenario.expected.outcome
    if expected in {"unavailable", "invalid"}:
        if state != expected:
            _add(findings, "coach_evaluation_fallback_unclassified")
        if output.get("scores") or output.get("overall") is not None:
            _add(findings, "coach_evaluation_fallback_unclassified")
        return
    if state != "completed":
        _add(findings, "coach_evaluation_fallback_unclassified")
        return
    scores = output.get("scores")
    if not isinstance(scores, dict) or set(scores) != _EVALUATION_DIMENSIONS:
        _add(findings, "coach_evaluation_dimension_missing")
        return
    if any(
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not 0 <= float(value) <= 10
        for value in scores.values()
    ):
        _add(findings, "coach_evaluation_score_out_of_range")
    overall = output.get("overall")
    if not isinstance(overall, int | float) or isinstance(overall, bool):
        _add(findings, "coach_evaluation_score_out_of_range")
    elif abs(float(overall) - sum(float(item) for item in scores.values()) / len(scores)) > 1:
        _add(findings, "coach_evaluation_overall_inconsistent")


def _validate_rubric(
    scenario: CoachScenario, output: dict[str, Any], findings: list[ValidationFinding]
) -> None:
    dimensions = output.get("dimensions")
    if not isinstance(dimensions, dict):
        _add(findings, "coach_rubric_dimension_missing")
        return
    aliases = {
        "content": "relevance",
        "structure": "star_structure",
        "delivery": "communication",
        "specificity": "impact_metrics",
    }
    for key, expected in scenario.input["baseline_scores"].items():
        observed = dimensions.get(aliases.get(key, key), {})
        if not isinstance(observed, dict) or observed.get("score") != expected:
            _add(findings, "coach_rubric_score_mutation")


def _validate_report(
    scenario: CoachScenario, output: dict[str, Any], findings: list[ValidationFinding]
) -> None:
    if output.get("report_state") not in {"completed", "fallback"}:
        _add(findings, "coach_report_fallback_unclassified")
    authoritative = scenario.input["authoritative_report"]
    count_fields = (
        "question_count_total",
        "question_count_evaluated",
        "question_count_skipped",
        "question_count_unavailable",
    )
    if any(output.get(field, 0) != authoritative.get(field, 0) for field in count_fields):
        _add(findings, "coach_report_count_mismatch")
    if output.get("overall_score") != authoritative.get("overall_score") or output.get(
        "category_scores"
    ) != authoritative.get("category_scores"):
        _add(findings, "coach_report_score_mutation")


def _validate_drill(output: dict[str, Any], findings: list[ValidationFinding]) -> None:
    drills = output.get("drills")
    if not isinstance(drills, list) or not drills:
        _add(findings, "coach_drill_schema_invalid")
        return
    for drill in drills:
        if not isinstance(drill, dict) or not all(
            isinstance(drill.get(field), str) and drill[field].strip()
            for field in ("walkthrough", "drill_prompt")
        ):
            _add(findings, "coach_drill_schema_invalid")
        elif len(drill["walkthrough"].split()) > 200:
            _add(findings, "coach_drill_length_exceeded")


def validate_execution(
    scenario: CoachScenario, execution: StageExecution
) -> ValidationResult:
    findings: list[ValidationFinding] = []
    expected_harness = _EXPECTED_HARNESS_GATES.get(scenario.scenario_id, set())
    for code in execution.gate_codes:
        _add(
            findings,
            code,
            blocking=code not in _NON_BLOCKING_GATES and code not in expected_harness,
        )
    output = execution.output
    if scenario.stage == "question_generation":
        _validate_question_generation(scenario, output, findings)
    elif scenario.stage == "model_answer":
        _validate_model_answer(scenario, execution, output, findings)
    elif scenario.stage == "answer_evaluation":
        _validate_answer_evaluation(scenario, output, findings)
    elif scenario.stage == "rubric_synthesis":
        _validate_rubric(scenario, output, findings)
    elif scenario.stage == "session_report":
        _validate_report(scenario, output, findings)
    elif scenario.stage == "technical_drill":
        _validate_drill(output, findings)
    elif scenario.stage == "company_research":
        if output.get("verification_state") not in {
            "verified",
            "partially_verified",
            "not_verified",
        }:
            _add(findings, "coach_stage_failed")
        source_ids = {
            str(item.get("source_id"))
            for item in output.get("sources", [])
            if isinstance(item, dict)
        }
        allowed_sources = set(scenario.scoring.allowed_source_ids)
        if allowed_sources and source_ids - allowed_sources:
            _add(findings, "coach_stage_failed")
        rendered = str(output).casefold()
        if "ignore previous instructions" in rendered:
            _add(findings, "coach_question_prompt_injection_followed")
    return ValidationResult(tuple(findings))
