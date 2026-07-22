"""Contract tests for canonical Coach aggregation and immutable reports."""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.coach import AnswerEvaluation, RubricDimension, SessionRubric
from app.services.coach_aggregation import (
    aggregate_session_rubric,
    build_deterministic_report,
    resolve_canonical_attempts,
)
from app.services.feedback_generator import FeedbackGeneratorService


def _question(question_id: str, order: int, category: str = "Technical"):
    return SimpleNamespace(
        id=question_id,
        text=f"Question {order}",
        category=category,
        order_in_session=order,
    )


def _recording(
    recording_id: str,
    question_id: str,
    state: str,
    created_at: datetime,
    score: float | None = None,
    *,
    dimension_score: int | None = None,
):
    payload = None
    if state == "completed" and score is not None:
        dim_score = dimension_score if dimension_score is not None else int(score)
        evaluation = AnswerEvaluation(
            scores={name: dim_score for name in (
                "relevance", "star_structure", "technical_depth",
                "conciseness", "communication", "impact_metrics",
            )},
            overall=score,
            strengths=[f"Evidence {recording_id}"],
            improvements=[f"Improve {recording_id}"],
            rubric=SessionRubric(
                dimensions={
                    "relevance": RubricDimension(
                        score=dim_score,
                        score_band="good",
                        evidence=[f"Evidence {recording_id}"],
                        drill="Practise relevance.",
                    )
                }
            ),
        )
        payload = evaluation.model_dump_json()
    return SimpleNamespace(
        id=recording_id,
        question_id=question_id,
        evaluation_state=state,
        evaluation_json=payload,
        created_at=created_at,
        speech_metrics=None,
    )


def test_report_uses_latest_completed_not_latest_failed_retry() -> None:
    now = datetime.utcnow()
    questions = [_question("q1", 1)]
    recordings = [
        _recording("r1", "q1", "completed", now, 7.5),
        _recording("r2", "q1", "failed", now + timedelta(seconds=1)),
    ]

    report = build_deterministic_report("s1", questions, recordings)

    assert report.question_count_evaluated == 1
    assert report.question_count_unavailable == 0
    assert report.overall_score == 7.5


def test_counts_are_unique_questions_and_no_score_is_null() -> None:
    now = datetime.utcnow()
    questions = [_question("q1", 1), _question("q2", 2), _question("q3", 3)]
    recordings = [
        _recording("r1", "q1", "invalid", now),
        _recording("r2", "q1", "failed", now + timedelta(seconds=1)),
        _recording("r3", "q2", "skipped", now),
    ]

    report = build_deterministic_report("s1", questions, recordings)

    assert report.overall_score is None
    assert report.category_scores == {}
    assert (
        report.question_count_evaluated
        + report.question_count_skipped
        + report.question_count_unavailable
        + report.question_count_unanswered
    ) == report.question_count_total == 3
    assert report.question_count_unavailable == 1
    assert report.question_count_skipped == 1
    assert report.question_count_unanswered == 1


def test_round_half_up_and_recording_id_tie_break_are_authoritative() -> None:
    now = datetime.utcnow()
    questions = [_question("q1", 1), _question("q2", 2)]
    recordings = [
        _recording("r1", "q1", "completed", now, 6.24, dimension_score=6),
        _recording("r2", "q1", "completed", now, 8.0, dimension_score=8),
        _recording("r3", "q2", "completed", now, 6.25, dimension_score=7),
    ]

    resolved = resolve_canonical_attempts(questions, recordings)
    report = build_deterministic_report("s1", questions, recordings)
    rubric = aggregate_session_rubric(resolved)

    assert resolved[0].recording.id == "r2"
    assert report.overall_score == 7.1
    assert rubric.dimensions["relevance"].score == 8


@pytest.mark.asyncio
async def test_report_model_cannot_mutate_authoritative_values() -> None:
    now = datetime.utcnow()
    questions = [_question("q1", 1)]
    recordings = [_recording("r1", "q1", "completed", now, 7.5)]
    base = build_deterministic_report("s1", questions, recordings)
    client = MagicMock(model="configured-model")
    client.complete_json = AsyncMock(return_value={
        "overall_score": 10,
        "question_count_total": 99,
        "executive_summary": "Keep practising the documented answer.",
        "strengths": [],
        "improvement_areas": [],
        "coaching_points": [],
        "practice_plan": [],
    })

    report = await FeedbackGeneratorService(client).generate_report(
        session_id="s1",
        role_title="Engineer",
        company_name="Example",
        question_evaluations=[],
        deterministic_report=base,
    )

    assert report.overall_score == 7.5
    assert report.question_count_total == 1
    assert report.report_state == "fallback"
    assert report.diagnostic is not None
    assert "coach_report_score_mutation" in report.diagnostic.gate_codes
    assert "coach_report_count_mismatch" in report.diagnostic.gate_codes


@pytest.mark.asyncio
async def test_report_provider_failure_returns_deterministic_fallback() -> None:
    base = build_deterministic_report("s1", [_question("q1", 1)], [])
    client = MagicMock(model="configured-model")
    client.complete_json = AsyncMock(side_effect=RuntimeError("offline"))

    report = await FeedbackGeneratorService(client).generate_report(
        session_id="s1",
        role_title="Engineer",
        company_name="Example",
        question_evaluations=[],
        deterministic_report=base,
    )

    assert report.report_state == "fallback"
    assert report.overall_score is None
    assert report.diagnostic is not None
    assert report.diagnostic.gate_codes == ["coach_report_provider_unavailable"]
