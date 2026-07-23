"""Stable Coach span and metric names used through the shared facade."""

from __future__ import annotations

COACH_STAGE_DURATION = "hatch.coach.stage.duration"
COACH_STAGE_OUTCOMES = "hatch.coach.stage.outcomes"
COACH_QUESTION_GENERATION_COUNT = "hatch.coach.question_generation.count"
COACH_MODEL_ANSWER_OUTCOMES = "hatch.coach.model_answer.outcomes"
COACH_EVALUATION_OUTCOMES = "hatch.coach.evaluation.outcomes"
COACH_RUBRIC_OUTCOMES = "hatch.coach.rubric.outcomes"
COACH_REPORT_OUTCOMES = "hatch.coach.report.outcomes"
COACH_ASYNC_JOB_OUTCOMES = "hatch.coach.async_job.outcomes"

COACH_OUTCOME_METRICS = {
    "model_answer": COACH_MODEL_ANSWER_OUTCOMES,
    "evaluation": COACH_EVALUATION_OUTCOMES,
    "rubric": COACH_RUBRIC_OUTCOMES,
    "report": COACH_REPORT_OUTCOMES,
    "async_job": COACH_ASYNC_JOB_OUTCOMES,
}


def metric_stage_name(span_name: str) -> str:
    """Convert an exact Coach span name to a bounded metric dimension."""
    normalized = span_name.removeprefix("coach.").replace(".", "_")
    return normalized[:128]
