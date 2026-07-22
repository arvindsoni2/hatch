from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from app.config import settings
from app.models.coach_session import InterviewSession, SessionQuestion, SessionRecording
from app.schemas.coach import AnswerEvaluation, SessionFeedbackReport, SessionQuestionRead
from app.services.coach_contracts import (
    COACH_VALIDATION_SCHEMA_VERSION,
    CoachDiagnostic,
    contains_candidate_history_claim,
    candidate_name_aliases,
    merge_stage_diagnostic,
    run_with_stage_deadline,
)

Settings = type(settings)


def test_candidate_history_detector_handles_irregular_name_without_imperative_false_positive() -> None:
    for claim in (
        "Alex wrote the migration plan for Acme.",
        "Alex chose the migration approach.",
        "Alex was responsible for the Acme migration.",
        "Alex owns the migration program at Acme.",
        "Alex has written the migration plan.",
        "The candidate was responsible for the migration.",
        "Alex pioneered the migration for Acme.",
        "Alex leads the migration program at Acme.",
        "Alex pioneered cloud migration for Acme.",
        "Alex pioneered Project Phoenix.",
        "Alex set priorities for the migration.",
        "Alex cut costs at Acme.",
    ):
        assert contains_candidate_history_claim(claim, candidate_names=("Alex",))
    for recommendation in (
        "Use examples tailored to the role.",
        "Include tailored examples in the next answer.",
        "Record completed answers for review.",
        "Add tailored examples to the next answer.",
        "Rehearse completed answers before the interview.",
        "Provide tailored examples in the next answer.",
        "Share completed examples during practice.",
        "Provide improved examples in the next answer.",
        "Share improved examples during practice.",
    ):
        assert not contains_candidate_history_claim(recommendation)

    assert contains_candidate_history_claim(
        "Alex refactored cloud migration workflows.",
        candidate_names=("Alex",),
    )
    for progressive_claim in (
        "Alex is leading the Acme migration.",
        "Alex has been leading the Acme migration.",
    ):
        assert contains_candidate_history_claim(
            progressive_claim, candidate_names=("Alex Smith", "Alex")
        )
    for recommendation in (
        "Alex should provide improved examples.",
        "Alex can use structured examples.",
    ):
        assert not contains_candidate_history_claim(
            recommendation, candidate_names=("Alex Smith", "Alex")
        )
    assert candidate_name_aliases("  Alex   Smith ") == ("Alex Smith", "Alex")



def test_deterministic_diagnostic_allows_nullable_prompt_fields() -> None:
    diagnostic = CoachDiagnostic(
        stage="session_rubric_aggregation",
        outcome="completed",
        execution_mode="deterministic",
        attempt_count=0,
        repair_count=0,
        gate_codes=[],
        duration_ms=1,
    )

    assert diagnostic.validation_schema_version == COACH_VALIDATION_SCHEMA_VERSION
    assert diagnostic.prompt_id is None
    assert diagnostic.prompt_version is None
    assert diagnostic.output_schema_version is None
    assert diagnostic.model_id is None


@pytest.mark.parametrize("missing", ["prompt_id", "prompt_version", "model_id"])
def test_llm_diagnostic_requires_prompt_and_model_metadata(missing: str) -> None:
    payload = {
        "stage": "model_answer",
        "outcome": "completed",
        "execution_mode": "llm",
        "prompt_id": "model_answer",
        "prompt_version": "2.0.0",
        "output_schema_version": "1.0.0",
        "model_id": "configured-model",
        "attempt_count": 1,
        "repair_count": 0,
        "gate_codes": [],
        "duration_ms": 1,
    }
    payload[missing] = None

    with pytest.raises(ValidationError):
        CoachDiagnostic(**payload)


def test_llm_diagnostic_requires_at_least_one_attempt() -> None:
    with pytest.raises(ValidationError):
        CoachDiagnostic(
            stage="model_answer",
            outcome="completed",
            execution_mode="llm",
            prompt_id="model_answer",
            prompt_version="2.0.0",
            output_schema_version="1.0.0",
            model_id="configured-model",
            attempt_count=0,
            repair_count=0,
            gate_codes=[],
            duration_ms=1,
        )


def test_non_llm_diagnostic_rejects_prompt_or_model_metadata() -> None:
    with pytest.raises(ValidationError):
        CoachDiagnostic(
            stage="session_report",
            outcome="fallback_deterministic",
            execution_mode="deterministic",
            prompt_id="session_report",
            prompt_version="2.0.0",
            model_id="configured-model",
            attempt_count=0,
            repair_count=0,
            gate_codes=["coach_report_provider_unavailable"],
            duration_ms=1,
        )


def test_diagnostic_rejects_unknown_stage_outcome_and_gate_code() -> None:
    common = {
        "execution_mode": "not_run",
        "attempt_count": 0,
        "repair_count": 0,
        "gate_codes": [],
        "duration_ms": 0,
    }
    with pytest.raises(ValidationError):
        CoachDiagnostic(stage="unknown", outcome="completed", **common)
    with pytest.raises(ValidationError):
        CoachDiagnostic(stage="model_answer", outcome="unavailable_timeout", **common)
    with pytest.raises(ValidationError):
        CoachDiagnostic(
            stage="model_answer",
            outcome="unavailable",
            **{**common, "gate_codes": ["made_up_gate"]},
        )


def test_merge_stage_diagnostic_preserves_existing_stage_keys() -> None:
    existing = {
        "schema_version": "1.0.0",
        "stages": {"company_research": {"final": {"outcome": "completed"}}},
    }

    merged = merge_stage_diagnostic(
        existing,
        "question_generation",
        {"final": {"outcome": "completed"}},
    )

    assert set(merged["stages"]) == {"company_research", "question_generation"}
    assert existing["stages"] == {"company_research": {"final": {"outcome": "completed"}}}


@pytest.mark.asyncio
async def test_stage_deadline_times_out_once_without_retrying() -> None:
    calls = 0

    async def slow_call() -> str:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return "late"

    with pytest.raises(TimeoutError):
        await run_with_stage_deadline(slow_call(), 0.001)
    assert calls == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("HATCH_COACH_TIMEOUT_MODEL_ANSWER_SECONDS", 9),
        ("HATCH_COACH_TIMEOUT_SESSION_CREATE_JOB_SECONDS", 59),
        ("HATCH_COACH_STALE_JOB_GRACE_SECONDS", 29),
    ],
)
def test_coach_timeout_settings_reject_out_of_range(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value})


def test_coach_timeout_settings_have_locked_defaults() -> None:
    configured = Settings()

    assert configured.HATCH_COACH_TIMEOUT_COMPANY_RESEARCH_SECONDS == 180
    assert configured.HATCH_COACH_TIMEOUT_QUESTION_GENERATION_SECONDS == 300
    assert configured.HATCH_COACH_TIMEOUT_QUESTION_REPAIR_SECONDS == 180
    assert configured.HATCH_COACH_TIMEOUT_MODEL_ANSWER_SECONDS == 180
    assert configured.HATCH_COACH_TIMEOUT_ANSWER_EVALUATION_SECONDS == 300
    assert configured.HATCH_COACH_TIMEOUT_RUBRIC_ENRICHMENT_SECONDS == 120
    assert configured.HATCH_COACH_TIMEOUT_TECHNICAL_DRILL_SECONDS == 120
    assert configured.HATCH_COACH_TIMEOUT_SESSION_REPORT_SECONDS == 300
    assert configured.HATCH_COACH_TIMEOUT_SESSION_CREATE_JOB_SECONDS == 2400
    assert configured.HATCH_COACH_TIMEOUT_ANSWER_SUBMIT_JOB_SECONDS == 600
    assert configured.HATCH_COACH_TIMEOUT_SESSION_END_JOB_SECONDS == 600
    assert configured.HATCH_COACH_TIMEOUT_FOLLOWUP_SECONDS == 60
    assert configured.HATCH_COACH_STALE_JOB_GRACE_SECONDS == 120


def test_coach_models_expose_additive_c1_columns() -> None:
    assert {
        "diagnostics",
        "report_json",
        "report_state",
        "report_job_id",
        "report_started_at",
        "activity_version",
    } <= set(InterviewSession.__table__.columns.keys())
    assert {"requirement_id", "model_answer_diagnostics"} <= set(
        SessionQuestion.__table__.columns.keys()
    )
    assert {"evaluation_state", "async_job_id"} <= set(
        SessionRecording.__table__.columns.keys()
    )


def test_historical_evaluation_without_new_fields_remains_readable() -> None:
    historical = AnswerEvaluation(
        scores={"relevance": 7},
        overall=7.0,
        feedback="Useful",
    )

    assert historical.evaluation_state == "completed"
    assert historical.diagnostic is None
    assert historical.overall == 7.0


def test_unavailable_evaluation_supports_absent_score_and_rubric() -> None:
    evaluation = AnswerEvaluation(
        evaluation_state="unavailable",
        scores={},
        overall=None,
        rubric=None,
    )

    assert evaluation.scores == {}
    assert evaluation.overall is None
    assert evaluation.rubric is None


def test_unavailable_evaluation_rejects_numeric_fallback() -> None:
    with pytest.raises(ValidationError):
        AnswerEvaluation(
            evaluation_state="unavailable",
            scores={"relevance": 5},
            overall=5.0,
        )


def test_historical_report_and_question_payloads_remain_readable() -> None:
    report = SessionFeedbackReport(session_id="s1", overall_score=8.0)
    question = SessionQuestionRead(
        id="q1",
        question_num=1,
        text="Question?",
        category="Technical",
        difficulty="medium",
        order_in_session=1,
    )

    assert report.report_state == "completed"
    assert report.question_count_total == 0
    assert report.diagnostic is None
    assert question.requirement_id is None
    assert question.model_answer_diagnostics is None
