from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.models.coach_session import InterviewSession, SessionQuestion, SessionRecording
from app.observability import runtime as runtime_module
from app.observability.runtime import TelemetryRuntime
from app.observability.attributes import COACH_GATE_CODE, COACH_OUTCOME
from app.routers.coach import _answer_job_timeout_result
from app.schemas.coach import (
    AnswerEvaluation,
    CreateSessionRequest,
    ModelAnswerResult,
    QuestionPresentation,
    SessionRubric,
    SubmitAnswerRequest,
)
from app.services.coach_contracts import CoachDiagnostic
from app.services.coach_service import CoachService


class _Instrument:
    def __init__(self) -> None:
        self.calls: list[tuple[int | float, dict[str, object]]] = []

    def add(self, value, attributes) -> None:
        self.calls.append((value, attributes))

    def record(self, value, attributes) -> None:
        self.calls.append((value, attributes))


class _Meter:
    def __init__(self) -> None:
        self.instruments: dict[str, _Instrument] = {}

    def create_counter(self, name, **_kwargs):
        return self.instruments.setdefault(name, _Instrument())

    def create_histogram(self, name, **_kwargs):
        return self.instruments.setdefault(name, _Instrument())


class _RawSpan:
    def __init__(self, name: str, attributes: dict[str, object]) -> None:
        self.name = name
        self.attributes = attributes
        self.events: list[object] = []

    def set_attribute(self, key, value) -> None:
        self.attributes[key] = value

    def add_event(self, name, attributes) -> None:
        self.events.append(SimpleNamespace(name=name, attributes=attributes))

    def set_status(self, *_args, **_kwargs) -> None:
        return None


class _SpanManager:
    def __init__(self, span: _RawSpan) -> None:
        self.span = span

    def __enter__(self) -> _RawSpan:
        return self.span

    def __exit__(self, *_args) -> bool:
        return False


class _Tracer:
    def __init__(self) -> None:
        self.spans: list[_RawSpan] = []

    def start_as_current_span(self, name, attributes=None, **_kwargs) -> _SpanManager:
        span = _RawSpan(name, dict(attributes or {}))
        self.spans.append(span)
        return _SpanManager(span)


class _Exporter:
    def __init__(self, tracer: _Tracer) -> None:
        self.tracer = tracer

    def get_finished_spans(self) -> list[_RawSpan]:
        return self.tracer.spans


def _recording_runtime() -> tuple[TelemetryRuntime, _Exporter, _Meter]:
    tracer = _Tracer()
    exporter = _Exporter(tracer)
    meter = _Meter()
    return (
        TelemetryRuntime(
            status="active",
            tracer=tracer,
            meter=meter,
        ),
        exporter,
        meter,
    )


@pytest.mark.asyncio
async def test_span_and_metric_failures_do_not_change_coach_database_state(
    db_session,
    monkeypatch,
) -> None:
    class BrokenTracer:
        def start_as_current_span(self, *_args, **_kwargs):
            raise RuntimeError("span exporter unavailable")

    class BrokenInstrument:
        def add(self, *_args, **_kwargs):
            raise RuntimeError("metric exporter unavailable")

        def record(self, *_args, **_kwargs):
            raise RuntimeError("metric exporter unavailable")

    class BrokenMeter:
        def create_counter(self, *_args, **_kwargs):
            return BrokenInstrument()

        def create_histogram(self, *_args, **_kwargs):
            return BrokenInstrument()

    monkeypatch.setattr(
        runtime_module,
        "_runtime",
        TelemetryRuntime(
            status="active",
            tracer=BrokenTracer(),
            meter=BrokenMeter(),
        ),
    )
    db_session.add(
        InterviewSession(
            id="session-telemetry-failure",
            company_name="Synthetic Company",
            role_title="Synthetic Role",
            config={"question_count": 1},
            status="active",
        )
    )
    db_session.add(
        SessionQuestion(
            id="question-telemetry-failure",
            session_id="session-telemetry-failure",
            question_num=1,
            text="Synthetic private question sentinel",
            category="Behavioural",
            difficulty="medium",
            order_in_session=1,
        )
    )
    await db_session.commit()
    service = CoachService()
    unavailable = _answer_job_timeout_result()
    service._evaluator.evaluate = AsyncMock(return_value=unavailable)

    result = await service.submit_answer(
        "session-telemetry-failure",
        "question-telemetry-failure",
        SubmitAnswerRequest(transcript="Synthetic private transcript sentinel"),
        db_session,
    )

    assert result.evaluation_state == "unavailable"
    recording = (
        await db_session.execute(
            select(SessionRecording).where(
                SessionRecording.session_id == "session-telemetry-failure"
            )
        )
    ).scalar_one()
    assert recording.evaluation_state == "unavailable"
    assert recording.transcript == "Synthetic private transcript sentinel"


@pytest.mark.asyncio
async def test_unavailable_diagnostic_is_observable_without_private_content(
    db_session,
    monkeypatch,
) -> None:
    telemetry, exporter, _meter = _recording_runtime()
    monkeypatch.setattr(
        runtime_module,
        "_runtime",
        telemetry,
    )
    db_session.add(
        InterviewSession(
            id="session-private-content",
            company_name="Private company sentinel",
            role_title="Private role sentinel",
            config={"question_count": 1},
            status="active",
        )
    )
    db_session.add(
        SessionQuestion(
            id="question-private-content",
            session_id="session-private-content",
            question_num=1,
            text="Private question sentinel",
            category="Behavioural",
            difficulty="medium",
            order_in_session=1,
        )
    )
    await db_session.commit()
    unavailable = AnswerEvaluation(
        evaluation_state="unavailable",
        diagnostic=CoachDiagnostic(
            stage="answer_evaluation",
            outcome="unavailable",
            execution_mode="deterministic",
            attempt_count=0,
            repair_count=0,
            gate_codes=["coach_evaluation_provider_unavailable"],
            duration_ms=0,
        ),
        scores={},
        overall=None,
        retryable=True,
    )
    service = CoachService()
    service._evaluator.evaluate = AsyncMock(return_value=unavailable)

    result = await service.submit_answer(
        "session-private-content",
        "question-private-content",
        SubmitAnswerRequest(
            transcript="Private transcript sentinel",
            audio_uri="/home/private/audio-sentinel.wav",
        ),
        db_session,
    )

    assert result.evaluation_state == "unavailable"
    spans = exporter.get_finished_spans()
    evaluation_span = next(
        span for span in spans if span.name == "coach.answer_evaluation"
    )
    assert evaluation_span.attributes[COACH_OUTCOME] == "unavailable"
    assert [(event.name, event.attributes) for event in evaluation_span.events] == [
        (
            "coach_gate",
            {COACH_GATE_CODE: "coach_evaluation_provider_unavailable"},
        )
    ]
    exported = repr(
        [
            (span.name, span.attributes, span.events)
            for span in exporter.get_finished_spans()
        ]
    )
    for sentinel in (
        "Private company sentinel",
        "Private role sentinel",
        "Private question sentinel",
        "Private transcript sentinel",
        "audio-sentinel.wav",
    ):
        assert sentinel not in exported


@pytest.mark.asyncio
async def test_rubric_fallback_diagnostic_sets_span_and_metric_outcome(
    db_session,
    monkeypatch,
) -> None:
    telemetry, exporter, meter = _recording_runtime()
    monkeypatch.setattr(runtime_module, "_runtime", telemetry)
    db_session.add(
        InterviewSession(
            id="session-rubric-fallback",
            company_name="Synthetic Company",
            role_title="Synthetic Role",
            config={"question_count": 1},
            status="active",
        )
    )
    db_session.add(
        SessionQuestion(
            id="question-rubric-fallback",
            session_id="session-rubric-fallback",
            question_num=1,
            text="Describe a project.",
            category="Behavioural",
            difficulty="medium",
            order_in_session=1,
        )
    )
    await db_session.commit()
    completed = AnswerEvaluation(overall=5.0)
    fallback_rubric = SessionRubric(
        diagnostic=CoachDiagnostic(
            stage="rubric_synthesis",
            outcome="fallback_deterministic",
            execution_mode="deterministic",
            attempt_count=0,
            repair_count=0,
            gate_codes=["coach_rubric_provider_unavailable"],
            duration_ms=0,
        )
    )
    service = CoachService()
    service._evaluator.evaluate = AsyncMock(return_value=completed)
    service._rubric_synthesiser.synthesise = AsyncMock(return_value=fallback_rubric)

    await service.submit_answer(
        "session-rubric-fallback",
        "question-rubric-fallback",
        SubmitAnswerRequest(transcript="A supported answer."),
        db_session,
    )

    span = next(
        item
        for item in exporter.get_finished_spans()
        if item.name == "coach.rubric_synthesis"
    )
    assert span.attributes[COACH_OUTCOME] == "fallback_deterministic"
    assert meter.instruments["hatch.coach.rubric.outcomes"].calls == [
        (1, {COACH_OUTCOME: "fallback_deterministic"})
    ]


@pytest.mark.asyncio
async def test_report_fallback_sets_span_and_metric_outcome(
    db_session,
    monkeypatch,
) -> None:
    telemetry, exporter, meter = _recording_runtime()
    monkeypatch.setattr(runtime_module, "_runtime", telemetry)
    db_session.add(
        InterviewSession(
            id="session-report-fallback",
            company_name="Synthetic Company",
            role_title="Synthetic Role",
            config={"question_count": 1},
            status="active",
        )
    )
    db_session.add(
        SessionQuestion(
            id="question-report-fallback",
            session_id="session-report-fallback",
            question_num=1,
            text="Describe a project.",
            category="Behavioural",
            difficulty="medium",
            order_in_session=1,
        )
    )
    await db_session.commit()

    report = await CoachService().end_session(
        "session-report-fallback",
        db_session,
        deterministic_only=True,
    )

    assert report.report_state == "fallback"
    span = next(
        item
        for item in exporter.get_finished_spans()
        if item.name == "coach.session_report"
    )
    assert span.attributes[COACH_OUTCOME] == "fallback"
    assert meter.instruments["hatch.coach.report.outcomes"].calls == [
        (1, {COACH_OUTCOME: "fallback"})
    ]


@pytest.mark.asyncio
async def test_model_answer_withholding_sets_span_and_metric_outcome(
    db_session,
    monkeypatch,
) -> None:
    telemetry, exporter, meter = _recording_runtime()
    monkeypatch.setattr(runtime_module, "_runtime", telemetry)
    withheld = CoachDiagnostic(
        stage="model_answer",
        outcome="withheld_insufficient_evidence",
        execution_mode="deterministic",
        attempt_count=0,
        repair_count=0,
        gate_codes=["coach_model_answer_no_evidence"],
        duration_ms=0,
    )
    service = CoachService.__new__(CoachService)
    service.research_company = AsyncMock(return_value=None)
    service._researcher = MagicMock(last_diagnostic=None)
    service._question_gen = MagicMock()
    service._question_gen.generate = AsyncMock(
        return_value=[
            QuestionPresentation(
                id="generated-1",
                text="Describe a migration.",
                category="Technical",
                difficulty="medium",
                num=1,
                total=1,
            )
        ]
    )
    service._model_answer_gen = MagicMock()
    service._model_answer_gen.generate = AsyncMock(
        return_value=ModelAnswerResult(
            model_answer="",
            diagnostic=withheld,
        )
    )
    service._drills = MagicMock()
    service._drills.build_drills = AsyncMock(
        side_effect=RuntimeError("optional drills unavailable")
    )

    with patch(
        "app.services.coach_service._load_candidate_summary",
        return_value="Synthetic evidence",
    ):
        result = await service.create_session(
            CreateSessionRequest(
                company_name="Synthetic Company",
                role_title="Synthetic Role",
                config={"question_count": 1},
            ),
            db_session,
        )

    assert result.status == "active"
    span = next(
        item
        for item in exporter.get_finished_spans()
        if item.name == "coach.model_answer.generate"
    )
    assert span.attributes[COACH_OUTCOME] == "withheld_insufficient_evidence"
    assert meter.instruments["hatch.coach.model_answer.outcomes"].calls == [
        (
            1,
            {
                "hatch.coach.model_answer_outcome": ("withheld_insufficient_evidence"),
                "hatch.coach.question_category": "Technical",
                COACH_OUTCOME: "withheld_insufficient_evidence",
            },
        )
    ]
