"""Runtime tracing built on Hatch's shared fail-open telemetry facade."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from app.observability.runtime import SafeSpan, TelemetryRuntime, get_telemetry

from .attributes import (
    RUNTIME_EXECUTION_ID,
    RUNTIME_TASK_ATTEMPT_ID,
    RUNTIME_TASK_ID,
    RUNTIME_TASK_VERSION,
    RUNTIME_WORKFLOW_RUN_ID,
    RUNTIME_WORKFLOW_STEP_ID,
)


@dataclass(frozen=True)
class RuntimeCorrelation:
    """The six durable runtime IDs that are trace-safe, never metric-safe."""

    workflow_run_id: str | None = None
    workflow_step_id: str | None = None
    task_attempt_id: str | None = None
    execution_id: str | None = None
    task_id: str | None = None
    task_version: int | None = None

    def trace_attributes(self) -> dict[str, str | int]:
        values = {
            RUNTIME_WORKFLOW_RUN_ID: self.workflow_run_id,
            RUNTIME_WORKFLOW_STEP_ID: self.workflow_step_id,
            RUNTIME_TASK_ATTEMPT_ID: self.task_attempt_id,
            RUNTIME_EXECUTION_ID: self.execution_id,
            RUNTIME_TASK_ID: self.task_id,
            RUNTIME_TASK_VERSION: self.task_version,
        }
        return {key: value for key, value in values.items() if value is not None}


class RuntimeTelemetry:
    """Thin runtime wrapper; it neither creates nor configures OTel providers."""

    def __init__(self, shared: TelemetryRuntime | None = None) -> None:
        self._shared = shared or get_telemetry()

    @contextmanager
    def span(self, name: str, correlation: RuntimeCorrelation) -> Iterator[SafeSpan]:
        """Start one shared-facade span and isolate every telemetry failure."""
        # TelemetryRuntime itself catches provider, processor, and exporter
        # failures. Keeping business exceptions outside this wrapper preserves
        # normal workflow semantics while the shared facade fails open.
        with self._shared.stage_span(
            "runtime", name, correlation.trace_attributes()
        ) as span:
            yield span
