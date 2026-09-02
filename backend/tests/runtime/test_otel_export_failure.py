"""Telemetry is observational only and must fail open."""

from __future__ import annotations

from app.observability.runtime import TelemetryRuntime
from app.runtime.observability import RuntimeCorrelation, RuntimeTelemetry


def test_exporter_failure_does_not_change_workflow_result() -> None:
    failures = 0

    class RawSpan:
        def set_attribute(self, *_args: object) -> None:
            return None

        def set_status(self, *_args: object) -> None:
            return None

    class Manager:
        def __enter__(self) -> RawSpan:
            return RawSpan()

        def __exit__(self, *_args: object) -> bool:
            nonlocal failures
            failures += 1
            raise RuntimeError("exporter unavailable")

    class FailingTracer:
        def start_as_current_span(self, *_args: object, **_kwargs: object) -> Manager:
            return Manager()

    telemetry = RuntimeTelemetry(
        TelemetryRuntime(status="active", tracer=FailingTracer())
    )

    with telemetry.span(
        "runtime.execution",
        RuntimeCorrelation(
            workflow_run_id="run-1", task_id="synthetic.echo", task_version=1
        ),
    ):
        result = {"code": "success"}

    assert result == {"code": "success"}
    assert failures == 1
