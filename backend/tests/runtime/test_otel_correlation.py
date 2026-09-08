"""Runtime-only, trace-safe OTel lineage correlation."""

from __future__ import annotations

from importlib.util import find_spec

import pytest

from app.observability.attributes import sanitize_metric_attributes
from app.observability.runtime import TelemetryRuntime
from app.runtime.observability import RuntimeCorrelation, RuntimeTelemetry


try:
    _HAS_OTEL_API = find_spec("opentelemetry.trace") is not None
except ModuleNotFoundError:
    _HAS_OTEL_API = False


def test_runtime_correlation_is_trace_safe_and_absent_from_metrics() -> None:
    started: list[dict[str, object]] = []

    class RawSpan:
        def set_attribute(self, *_args: object) -> None:
            return None

        def set_status(self, *_args: object) -> None:
            return None

    class Manager:
        def __enter__(self) -> RawSpan:
            return RawSpan()

        def __exit__(self, *_args: object) -> bool:
            return False

    class Tracer:
        def start_as_current_span(self, _name: str, **kwargs: object) -> Manager:
            started.append(kwargs)
            return Manager()

    correlation = RuntimeCorrelation(
        workflow_run_id="run-1",
        workflow_step_id="step-1",
        task_attempt_id="attempt-1",
        execution_id="execution-1",
        task_id="synthetic.evaluate",
        task_version=1,
    )
    telemetry = RuntimeTelemetry(TelemetryRuntime(status="active", tracer=Tracer()))

    with telemetry.span("runtime.evaluation", correlation):
        pass

    attributes = started[0]["attributes"]
    assert all(
        attributes[key] == value
        for key, value in correlation.trace_attributes().items()
    )
    assert sanitize_metric_attributes(attributes) == {
        "hatch.ai.workflow.name": "runtime"
    }
    assert started[0]["record_exception"] is False
    assert started[0]["set_status_on_exception"] is False


@pytest.mark.skipif(
    not _HAS_OTEL_API,
    reason="optional OpenTelemetry API is not installed in the core profile",
)
def test_runtime_telemetry_never_replaces_global_provider() -> None:
    from opentelemetry import trace

    provider = trace.get_tracer_provider()
    RuntimeTelemetry(TelemetryRuntime(status="disabled"))

    assert trace.get_tracer_provider() is provider


def test_content_exception_is_reduced_to_stable_status_code() -> None:
    started: list[dict[str, object]] = []
    safe_spans: list[object] = []

    class RawSpan:
        def set_attribute(self, *_args: object) -> None:
            return None

        def set_status(self, _status: object) -> None:
            return None

    class Manager:
        def __enter__(self) -> RawSpan:
            return RawSpan()

        def __exit__(self, *_args: object) -> bool:
            return False

    class Tracer:
        def start_as_current_span(self, _name: str, **kwargs: object) -> Manager:
            started.append(kwargs)
            return Manager()

    telemetry = RuntimeTelemetry(TelemetryRuntime(status="active", tracer=Tracer()))
    canary = "TRANSCRIPT-CANARY at /home/user/private.txt"
    with pytest.raises(RuntimeError, match="TRANSCRIPT-CANARY"):
        with telemetry.span(
            "runtime.model", RuntimeCorrelation(task_id="synthetic")
        ) as span:
            safe_spans.append(span)
            raise RuntimeError(canary)

    captured = repr((started, safe_spans[0].error_code))
    assert canary not in captured
    assert "/home/user/private.txt" not in captured
    assert "runtime_unhandled_error" in captured
