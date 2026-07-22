"""Pure canonical-attempt, session-rubric, and report aggregation."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Sequence

from ..schemas.coach import (
    AnswerEvaluation,
    QuestionEvaluationSummary,
    RubricDimension,
    SessionFeedbackReport,
    SessionRubric,
)
from .coach_contracts import CoachDiagnostic
from .rubric_builder import drill_for_dimension, score_to_band

_DIMENSION_PRIORITY = (
    "relevance",
    "star_structure",
    "technical_depth",
    "conciseness",
    "communication",
    "impact_metrics",
    "delivery",
    "vocal_confidence",
    "presence",
)
_TERMINAL_NO_SCORE = {"skipped", "unavailable", "invalid", "failed"}
_REQUIRED_SCORE_DIMENSIONS = {
    "relevance",
    "star_structure",
    "technical_depth",
    "conciseness",
    "communication",
    "impact_metrics",
}


@dataclass(frozen=True)
class CanonicalQuestion:
    """One question's canonical scored attempt and latest terminal state."""

    question: Any
    recording: Any | None
    evaluation: AnswerEvaluation | None
    latest_terminal_state: str | None


def _ordering(recording: Any) -> tuple[Any, str]:
    return recording.created_at, str(recording.id)


def _parse_completed(recording: Any) -> AnswerEvaluation | None:
    if recording.evaluation_state != "completed" or not recording.evaluation_json:
        return None
    try:
        raw = json.loads(recording.evaluation_json)
        evaluation = AnswerEvaluation.model_validate(raw)
    except Exception:
        return None
    if (
        evaluation.evaluation_state != "completed"
        or evaluation.overall is None
        or not 0 <= evaluation.overall <= 10
        or set(evaluation.scores) != _REQUIRED_SCORE_DIMENSIONS
        or any(not 0 <= score <= 10 for score in evaluation.scores.values())
    ):
        return None
    return evaluation


def resolve_canonical_attempts(
    questions: Sequence[Any], recordings: Sequence[Any]
) -> list[CanonicalQuestion]:
    """Resolve one latest valid completed attempt and one terminal state per question."""
    by_question: dict[str, list[Any]] = {}
    for recording in recordings:
        if recording.question_id is not None:
            by_question.setdefault(str(recording.question_id), []).append(recording)

    resolved: list[CanonicalQuestion] = []
    for question in sorted(questions, key=lambda item: (item.order_in_session, str(item.id))):
        attempts = by_question.get(str(question.id), [])
        completed = [
            (recording, evaluation)
            for recording in attempts
            if (evaluation := _parse_completed(recording)) is not None
        ]
        if completed:
            recording, evaluation = max(completed, key=lambda item: _ordering(item[0]))
        else:
            recording, evaluation = None, None
        terminal = [
            item for item in attempts if item.evaluation_state in _TERMINAL_NO_SCORE
        ]
        latest_state = (
            max(terminal, key=_ordering).evaluation_state if terminal else None
        )
        resolved.append(
            CanonicalQuestion(question, recording, evaluation, latest_state)
        )
    return resolved


def _normalise_evidence(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _aggregation_diagnostic() -> CoachDiagnostic:
    return CoachDiagnostic(
        stage="session_rubric_aggregation",
        outcome="completed",
        execution_mode="deterministic",
        attempt_count=0,
        repair_count=0,
        gate_codes=[],
        duration_ms=0,
    )


def aggregate_session_rubric(
    resolved: Sequence[CanonicalQuestion],
) -> SessionRubric:
    """Aggregate canonical answer rubrics with exact ordering and rounding."""
    dimension_rows: dict[str, list[tuple[int, int, Any, str, int, str]]] = {}
    dimension_scores: dict[str, list[int]] = {}
    for item in resolved:
        if item.recording is None or item.evaluation is None or item.evaluation.rubric is None:
            continue
        for dimension, rubric_dimension in item.evaluation.rubric.dimensions.items():
            dimension_scores.setdefault(dimension, []).append(rubric_dimension.score)
            for position, evidence in enumerate(rubric_dimension.evidence):
                dimension_rows.setdefault(dimension, []).append(
                    (
                        rubric_dimension.score,
                        item.question.order_in_session,
                        item.recording.created_at,
                        str(item.recording.id),
                        position,
                        evidence,
                    )
                )

    dimensions: dict[str, RubricDimension] = {}
    for dimension, scores in dimension_scores.items():
        rows = dimension_rows.get(dimension, [])
        mean = sum(Decimal(score) for score in scores) / Decimal(len(scores))
        score = int(mean.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

        evidence: list[str] = []
        seen: set[str] = set()
        for *_, value in sorted(rows, key=lambda row: row[:5]):
            normalised = _normalise_evidence(value)
            if normalised and normalised not in seen:
                seen.add(normalised)
                evidence.append(re.sub(r"\s+", " ", value).strip())
            if len(evidence) == 2:
                break
        dimensions[dimension] = RubricDimension(
            score=score,
            score_band=score_to_band(score),
            evidence=evidence,
            drill=drill_for_dimension(dimension),
        )

    selected = select_focus_dimensions(dimensions)
    focus = (
        "Focus next session on: "
        + " and ".join(name.replace("_", " ") for name in selected)
        + "."
        if selected
        else ""
    )
    return SessionRubric(
        dimensions=dimensions,
        focus_for_next_session=focus,
        diagnostic=_aggregation_diagnostic(),
    )


def select_focus_dimensions(
    dimensions: dict[str, RubricDimension],
) -> list[str]:
    """Select the exact one-or-two weakest dimensions using the C1 tie rules."""
    priority = {name: position for position, name in enumerate(_DIMENSION_PRIORITY)}
    ranked = sorted(
        dimensions,
        key=lambda name: (dimensions[name].score, priority.get(name, 999), name),
    )
    selected = ranked[:1]
    if len(ranked) > 1:
        lowest, second = dimensions[ranked[0]].score, dimensions[ranked[1]].score
        if second <= 6 or (lowest < 8 and second - lowest <= 1):
            selected.append(ranked[1])
    return selected


def _one_decimal(values: Sequence[float]) -> float:
    mean = sum(Decimal(str(value)) for value in values) / Decimal(len(values))
    return float(mean.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def build_deterministic_report(
    session_id: str,
    questions: Sequence[Any],
    recordings: Sequence[Any],
) -> SessionFeedbackReport:
    """Build authoritative report numbers and safe deterministic narrative inputs."""
    resolved = resolve_canonical_attempts(questions, recordings)
    completed = [item for item in resolved if item.evaluation is not None]
    skipped = sum(
        item.evaluation is None and item.latest_terminal_state == "skipped"
        for item in resolved
    )
    unavailable = sum(
        item.evaluation is None
        and item.latest_terminal_state in {"unavailable", "invalid", "failed"}
        for item in resolved
    )
    total = len(resolved)
    unanswered = max(0, total - len(completed) - skipped - unavailable)

    category_values: dict[str, list[float]] = {}
    summaries: list[QuestionEvaluationSummary] = []
    for item in completed:
        evaluation = item.evaluation
        assert evaluation is not None
        category_values.setdefault(item.question.category, []).append(evaluation.overall)
        summaries.append(
            QuestionEvaluationSummary(
                question_id=str(item.question.id),
                question_text=item.question.text,
                category=item.question.category,
                overall_score=evaluation.overall,
                scores=evaluation.scores,
                strengths=evaluation.strengths,
                improvements=evaluation.improvements,
            )
        )

    overall = _one_decimal([item.evaluation.overall for item in completed]) if completed else None
    category_scores = {
        category: _one_decimal(values) for category, values in category_values.items()
    }
    rubric = aggregate_session_rubric(resolved)
    ranked = sorted(
        rubric.dimensions.items(), key=lambda item: (-item[1].score, item[0])
    )
    weak = sorted(rubric.dimensions.items(), key=lambda item: (item[1].score, item[0]))
    return SessionFeedbackReport(
        session_id=session_id,
        report_state="completed",
        overall_score=overall,
        question_count_total=total,
        question_count_evaluated=len(completed),
        question_count_skipped=skipped,
        question_count_unavailable=unavailable,
        question_count_unanswered=unanswered,
        category_scores=category_scores,
        executive_summary=(
            f"{len(completed)} of {total} questions received a completed evaluation."
            if completed
            else "No answers received a completed evaluation."
        ),
        strengths=[dimension.evidence[0] for _, dimension in ranked if dimension.evidence][:2],
        improvement_areas=[name.replace("_", " ") for name, _ in weak[:2]],
        coaching_points=[dimension.drill for _, dimension in weak[:2] if dimension.drill],
        question_evaluations=summaries,
    )
