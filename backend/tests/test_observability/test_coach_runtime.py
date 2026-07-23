from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.observability import attributes as telemetry_attributes
from app.observability import runtime as runtime_module
from app.observability.attributes import (
    ASYNC_JOB_ID,
    BENCHMARK_CASE_ID,
    BENCHMARK_RUN_ID,
    COACH_GATE_CODE,
    COACH_OUTCOME,
    COACH_SESSION_ID,
    COACH_STAGE,
)
from app.observability.runtime import TelemetryRuntime, trace_workflow


@dataclass
class _Instrument:
    calls: list[tuple[float | int, dict[str, Any]]] = field(default_factory=list)

    def record(self, value: float, attributes: dict[str, Any]) -> None:
        self.calls.append((value, attributes))

    def add(self, value: int, attributes: dict[str, Any]) -> None:
        self.calls.append((value, attributes))


class _Meter:
    def __init__(self) -> None:
        self.instruments: dict[str, _Instrument] = {}

    def create_histogram(self, name: str, **_kwargs: Any) -> _Instrument:
        instrument = _Instrument()
        self.instruments[name] = instrument
        return instrument

    def create_counter(self, name: str, **_kwargs: Any) -> _Instrument:
        instrument = _Instrument()
        self.instruments[name] = instrument
        return instrument


class _RawSpan:
    def set_attribute(self, _key: str, _value: Any) -> None:
        return None


class _SpanManager(AbstractContextManager[_RawSpan]):
    def __enter__(self) -> _RawSpan:
        return _RawSpan()

    def __exit__(self, *_args: Any) -> bool:
        return False


class _Tracer:
    def __init__(self) -> None:
        self.names: list[str] = []

    def start_as_current_span(
        self,
        name: str,
        **_kwargs: Any,
    ) -> _SpanManager:
        self.names.append(name)
        return _SpanManager()


def test_coach_metric_attributes_drop_all_correlation_ids() -> None:
    safe = telemetry_attributes.sanitize_metric_attributes(
        {
            COACH_STAGE: "question_generation",
            COACH_OUTCOME: "completed",
            COACH_SESSION_ID: "session-1",
            ASYNC_JOB_ID: "job-1",
            BENCHMARK_RUN_ID: "run-1",
            BENCHMARK_CASE_ID: "scenario-1",
        }
    )

    assert safe == {
        COACH_STAGE: "question_generation",
        COACH_OUTCOME: "completed",
    }


def test_coach_stage_records_exact_span_and_bounded_metrics() -> None:
    tracer = _Tracer()
    meter = _Meter()
    runtime = TelemetryRuntime(status="active", tracer=tracer, meter=meter)

    with runtime.coach_stage_span(
        "coach.question_generation",
        {COACH_OUTCOME: "completed"},
    ):
        pass

    assert tracer.names == ["coach.question_generation"]
    duration = meter.instruments["hatch.coach.stage.duration"].calls
    outcomes = meter.instruments["hatch.coach.stage.outcomes"].calls
    assert len(duration) == 1
    assert duration[0][0] >= 0
    assert duration[0][1] == {
        COACH_STAGE: "question_generation",
        COACH_OUTCOME: "completed",
    }
    assert outcomes == [
        (
            1,
            {
                COACH_STAGE: "question_generation",
                COACH_OUTCOME: "completed",
            },
        )
    ]


def test_coach_diagnostic_updates_stage_outcome_and_emits_bounded_gates() -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    attributes: dict[str, Any] = {}

    class RawSpan:
        def set_attribute(self, key: str, value: Any) -> None:
            attributes[key] = value

        def add_event(self, name: str, event_attributes: dict[str, Any]) -> None:
            events.append((name, event_attributes))

    class SpanManager(AbstractContextManager[RawSpan]):
        def __enter__(self) -> RawSpan:
            return RawSpan()

        def __exit__(self, *_args: Any) -> bool:
            return False

    class Tracer:
        def start_as_current_span(self, *_args: Any, **_kwargs: Any) -> SpanManager:
            return SpanManager()

    meter = _Meter()
    runtime = TelemetryRuntime(status="active", tracer=Tracer(), meter=meter)

    with runtime.coach_stage_span("coach.answer_evaluation"):
        runtime.record_coach_diagnostic(
            "evaluation",
            "unavailable",
            ["coach_evaluation_provider_unavailable"],
            {COACH_SESSION_ID: "session-private"},
        )

    assert attributes[COACH_OUTCOME] == "unavailable"
    assert events == [
        (
            "coach_gate",
            {COACH_GATE_CODE: "coach_evaluation_provider_unavailable"},
        )
    ]
    assert meter.instruments["hatch.coach.stage.outcomes"].calls[-1] == (
        1,
        {
            COACH_STAGE: "answer_evaluation",
            COACH_OUTCOME: "unavailable",
        },
    )
    assert meter.instruments["hatch.coach.evaluation.outcomes"].calls == [
        (
            1,
            {
                COACH_OUTCOME: "unavailable",
            },
        )
    ]


def test_disabled_coach_runtime_creates_no_instruments_or_spans() -> None:
    tracer = _Tracer()
    meter = _Meter()
    runtime = TelemetryRuntime(status="disabled", tracer=tracer, meter=meter)

    with runtime.coach_stage_span("coach.session.create"):
        runtime.record_coach_question_count(
            4,
            {COACH_OUTCOME: "completed"},
        )

    assert tracer.names == []
    assert meter.instruments == {}


def test_coach_outcome_uses_only_allowlisted_family_and_dimensions() -> None:
    meter = _Meter()
    runtime = TelemetryRuntime(status="active", meter=meter)

    runtime.record_coach_outcome(
        "evaluation",
        "unavailable",
        {
            COACH_STAGE: "answer_evaluation",
            COACH_SESSION_ID: "session-1",
        },
    )
    runtime.record_coach_outcome("unsupported", "completed")

    assert meter.instruments["hatch.coach.evaluation.outcomes"].calls == [
        (
            1,
            {
                COACH_STAGE: "answer_evaluation",
                COACH_OUTCOME: "unavailable",
            },
        )
    ]


@pytest.mark.asyncio
async def test_workflow_decorator_forwards_static_coach_attributes(
    monkeypatch,
) -> None:
    observed: list[tuple[str, str, dict[str, Any]]] = []

    class _Runtime:
        def workflow_span(
            self,
            workflow: str,
            attributes: dict[str, Any] | None = None,
        ) -> _SpanManager:
            observed.append(("workflow", workflow, dict(attributes or {})))
            return _SpanManager()

        def coach_stage_span(
            self,
            stage: str,
            attributes: dict[str, Any] | None = None,
        ) -> _SpanManager:
            observed.append(("stage", stage, dict(attributes or {})))
            return _SpanManager()

    monkeypatch.setattr(runtime_module, "get_telemetry", lambda: _Runtime())

    @trace_workflow(
        "coach_generation",
        attributes={"hatch.coach.operation": "session_create"},
        stage="coach.session.create",
    )
    async def operation() -> str:
        return "unchanged"

    assert await operation() == "unchanged"
    assert observed == [
        (
            "workflow",
            "coach_generation",
            {"hatch.coach.operation": "session_create"},
        ),
        ("stage", "coach.session.create", {}),
    ]


@pytest.mark.asyncio
async def test_nested_stage_only_does_not_create_a_second_root(monkeypatch) -> None:
    observed: list[str] = []

    class _Runtime:
        @staticmethod
        def current_workflow(_default: str) -> str:
            return "coach_generation"

        def workflow_span(self, *_args, **_kwargs):
            raise AssertionError("nested workflow must not create a second root")

        def coach_stage_span(self, stage: str) -> _SpanManager:
            observed.append(stage)
            return _SpanManager()

    monkeypatch.setattr(runtime_module, "get_telemetry", lambda: _Runtime())

    @trace_workflow(
        "coach_generation",
        attributes={"hatch.coach.operation": "company_research"},
        stage="coach.company_research",
        nested_stage_only=True,
    )
    async def operation() -> str:
        return "unchanged"

    assert await operation() == "unchanged"
    assert observed == ["coach.company_research"]
