from __future__ import annotations

from dataclasses import FrozenInstanceError
from importlib.util import find_spec

import pytest

from app.observability.attributes import (
    ASYNC_JOB_ID,
    COACH_OPERATION,
    COACH_SESSION_ID,
)
from app.observability.runtime import TelemetryRuntime


try:
    _HAS_OTEL_SDK = find_spec("opentelemetry.sdk.trace") is not None
except ModuleNotFoundError:
    _HAS_OTEL_SDK = False


def _runtime_with_exporter():
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    runtime = TelemetryRuntime(
        status="active",
        tracer=provider.get_tracer("hatch.tests"),
        tracer_provider=provider,
    )
    return runtime, exporter


@pytest.mark.skipif(
    not _HAS_OTEL_SDK,
    reason="optional OpenTelemetry SDK is not installed in the core profile",
)
def test_background_workflow_has_one_link_and_no_request_parent() -> None:
    runtime, exporter = _runtime_with_exporter()

    with runtime.tracer.start_as_current_span("request") as request_span:
        request_context = request_span.get_span_context()
        token = runtime.capture_trace_context()

    with runtime.use_background_trace_context(
        token,
        {
            COACH_SESSION_ID: "session-1",
            ASYNC_JOB_ID: "job-1",
        },
    ):
        with runtime.workflow_span(
            "coach_generation",
            {COACH_OPERATION: "answer_submit"},
        ):
            pass

    spans = {span.name: span for span in exporter.get_finished_spans()}
    root = spans["hatch.ai.workflow.coach_generation"]
    assert root.parent is None
    assert len(root.links) == 1
    assert root.links[0].context == request_context
    assert root.attributes[COACH_SESSION_ID] == "session-1"
    assert root.attributes[ASYNC_JOB_ID] == "job-1"
    assert root.attributes[COACH_OPERATION] == "answer_submit"


def test_trace_context_token_is_frozen_and_empty_when_disabled() -> None:
    runtime = TelemetryRuntime(status="disabled")

    token = runtime.capture_trace_context()

    assert token.span_context is None
    with pytest.raises(FrozenInstanceError):
        token.span_context = object()  # type: ignore[misc]


def test_invalid_or_unavailable_trace_context_is_a_noop() -> None:
    class BrokenTracer:
        def start_as_current_span(self, *_args, **_kwargs):
            raise RuntimeError("exporter unavailable")

    runtime = TelemetryRuntime(status="active", tracer=BrokenTracer())
    token = runtime.capture_trace_context()

    with runtime.use_background_trace_context(token):
        with runtime.workflow_span("coach_generation"):
            result = {"unchanged": True}

    assert result == {"unchanged": True}
