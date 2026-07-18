"""Optional OpenTelemetry runtime behind a dependency-free Hatch facade."""
from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
from typing import Any, Literal

from .attributes import (
    FAILED_GATE_CODES,
    MODEL_ID,
    PROVIDER_TYPE,
    VALIDATION_STATE,
    WORKFLOW_NAME,
    sanitize_attributes,
)
from .logging import configure_log_correlation

logger = logging.getLogger(__name__)
TelemetryStatus = Literal["disabled", "active", "degraded"]


class SafeSpan:
    """Best-effort span adapter that never raises into business logic."""

    def __init__(self, span: Any = None) -> None:
        self._span = span

    def set_attribute(self, key: str, value: Any) -> None:
        attributes = sanitize_attributes({key: value})
        if self._span is None or key not in attributes:
            return
        try:
            self._span.set_attribute(key, attributes[key])
        except Exception:
            return

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        if self._span is None:
            return
        safe_name = name[:64] if isinstance(name, str) else "telemetry_event"
        try:
            self._span.add_event(safe_name, sanitize_attributes(attributes))
        except Exception:
            return

    def record_exception(self, exception: BaseException) -> None:
        if self._span is None:
            return
        try:
            self._span.record_exception(exception)
        except Exception:
            return

    def set_error(self, code: str) -> None:
        if self._span is None:
            return
        try:
            from opentelemetry.trace.status import Status, StatusCode

            self._span.set_status(Status(StatusCode.ERROR, code[:64]))
        except Exception:
            return


@dataclass(frozen=True)
class ShutdownResult:
    completed: bool
    timed_out: bool


class TelemetryRuntime:
    """Hatch-owned facade over optional SDK providers and instruments."""

    def __init__(
        self,
        *,
        status: TelemetryStatus,
        tracer: Any = None,
        meter: Any = None,
        tracer_provider: Any = None,
        meter_provider: Any = None,
    ) -> None:
        self.status = status
        self.tracer = tracer
        self.meter = meter
        self.tracer_provider = tracer_provider
        self.meter_provider = meter_provider
        self._warning_emitted = False
        self._warning_lock = threading.Lock()
        self._workflow_duration = self._histogram("hatch.ai.workflow.duration")
        self._model_duration = self._histogram("hatch.ai.model.call.duration")
        self._model_calls = self._counter("hatch.ai.model.calls")
        self._repair_calls = self._counter("hatch.ai.repair.calls")
        self._validation_failures = self._counter("hatch.ai.validation.failures")
        self._input_tokens = self._counter("hatch.ai.tokens.input")
        self._output_tokens = self._counter("hatch.ai.tokens.output")
        self._workflow_outcomes = self._counter("hatch.ai.workflow.outcomes")

    def _histogram(self, name: str) -> Any:
        if self.meter is None:
            return None
        try:
            return self.meter.create_histogram(name, unit="ms")
        except Exception:
            return None

    def _counter(self, name: str) -> Any:
        if self.meter is None:
            return None
        try:
            return self.meter.create_counter(name)
        except Exception:
            return None

    @contextmanager
    def _span(self, name: str, attributes: dict[str, Any] | None = None):
        if self.status != "active" or self.tracer is None:
            yield SafeSpan()
            return
        try:
            manager = self.tracer.start_as_current_span(
                name,
                attributes=sanitize_attributes(attributes),
            )
            raw_span = manager.__enter__()
        except Exception:
            yield SafeSpan()
            return
        span = SafeSpan(raw_span)
        try:
            yield span
        except BaseException as exc:
            span.record_exception(exc)
            span.set_error(type(exc).__name__)
            raise
        finally:
            try:
                manager.__exit__(None, None, None)
            except Exception:
                pass

    @contextmanager
    def workflow_span(
        self,
        workflow: str,
        attributes: dict[str, Any] | None = None,
    ):
        started = time.monotonic()
        safe_attributes = {WORKFLOW_NAME: workflow, **(attributes or {})}
        outcome = "completed"
        try:
            with self._span(
                f"hatch.ai.workflow.{workflow}",
                safe_attributes,
            ) as span:
                yield span
        except BaseException:
            outcome = "failed"
            raise
        finally:
            duration_ms = (time.monotonic() - started) * 1000
            self._record(self._workflow_duration, duration_ms, safe_attributes)
            self._add(
                self._workflow_outcomes,
                1,
                {WORKFLOW_NAME: workflow, VALIDATION_STATE: outcome},
            )

    @contextmanager
    def stage_span(
        self,
        workflow: str,
        stage: str,
        attributes: dict[str, Any] | None = None,
    ):
        with self._span(
            f"hatch.ai.stage.{stage}",
            {WORKFLOW_NAME: workflow, **(attributes or {})},
        ) as span:
            yield span

    @staticmethod
    def _record(instrument: Any, value: float, attributes: dict[str, Any]) -> None:
        if instrument is None:
            return
        try:
            instrument.record(value, sanitize_attributes(attributes))
        except Exception:
            return

    @staticmethod
    def _add(instrument: Any, value: int, attributes: dict[str, Any]) -> None:
        if instrument is None:
            return
        try:
            instrument.add(value, sanitize_attributes(attributes))
        except Exception:
            return

    def record_model_call(
        self,
        *,
        workflow: str,
        provider: str,
        model_id: str,
        duration_ms: float,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        attributes = {
            WORKFLOW_NAME: workflow,
            PROVIDER_TYPE: provider,
            MODEL_ID: model_id,
        }
        self._record(self._model_duration, duration_ms, attributes)
        self._add(self._model_calls, 1, attributes)
        if input_tokens is not None:
            self._add(self._input_tokens, input_tokens, attributes)
        if output_tokens is not None:
            self._add(self._output_tokens, output_tokens, attributes)

    def record_repair(self, workflow: str, repair_type: str) -> None:
        from .attributes import REPAIR_TYPE

        self._add(
            self._repair_calls,
            1,
            {WORKFLOW_NAME: workflow, REPAIR_TYPE: repair_type},
        )

    def record_validation_failure(self, workflow: str, gate_code: str) -> None:
        self._add(
            self._validation_failures,
            1,
            {WORKFLOW_NAME: workflow, FAILED_GATE_CODES: [gate_code]},
        )

    def _warn_once(self, message: str) -> None:
        with self._warning_lock:
            if self._warning_emitted:
                return
            self._warning_emitted = True
        logger.warning("%s", message)


_runtime = TelemetryRuntime(status="disabled")
_runtime_lock = threading.Lock()


def get_telemetry() -> TelemetryRuntime:
    return _runtime


def trace_workflow(workflow: str):
    """Decorate an async workflow with the current fail-open runtime."""

    def decorate(function):
        @wraps(function)
        async def wrapped(*args, **kwargs):
            with get_telemetry().workflow_span(workflow):
                return await function(*args, **kwargs)

        wrapped.__hatch_workflow__ = workflow
        return wrapped

    return decorate


def trace_stage(workflow: str, stage: str):
    """Decorate an async operation with a real workflow stage span."""

    def decorate(function):
        @wraps(function)
        async def wrapped(*args, **kwargs):
            with get_telemetry().stage_span(workflow, stage):
                return await function(*args, **kwargs)

        wrapped.__hatch_workflow__ = workflow
        wrapped.__hatch_stage__ = stage
        return wrapped

    return decorate


def _load_fastapi_instrumentor() -> Any:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    return FastAPIInstrumentor


def instrument_fastapi_app(app: Any, telemetry: TelemetryRuntime) -> bool:
    """Instrument one FastAPI app without capturing request data or headers."""
    if telemetry.status != "active":
        configure_log_correlation(enabled=False)
        return False
    try:
        _load_fastapi_instrumentor().instrument_app(
            app,
            tracer_provider=telemetry.tracer_provider,
            meter_provider=telemetry.meter_provider,
            exclude_spans=["receive", "send"],
        )
        configure_log_correlation(enabled=True)
    except Exception:
        telemetry.status = "degraded"
        telemetry._warn_once(
            "OpenTelemetry HTTP instrumentation failed; "
            "continuing with telemetry degraded."
        )
        return False
    return True


def shutdown_telemetry(deadline_seconds: float = 5.0) -> ShutdownResult:
    """Flush and close telemetry within one application-owned deadline."""
    telemetry = get_telemetry()
    providers = tuple(
        provider
        for provider in (telemetry.tracer_provider, telemetry.meter_provider)
        if provider is not None
    )
    if not providers:
        return ShutdownResult(completed=True, timed_out=False)

    failed = threading.Event()

    def flush_and_shutdown() -> None:
        for operation in ("force_flush", "shutdown"):
            for provider in providers:
                try:
                    getattr(provider, operation)()
                except Exception:
                    failed.set()

    thread = threading.Thread(
        target=flush_and_shutdown,
        name="hatch-telemetry-shutdown",
        daemon=True,
    )
    thread.start()
    thread.join(timeout=max(0.0, deadline_seconds))
    timed_out = thread.is_alive()
    if timed_out or failed.is_set():
        telemetry._warn_once(
            "OpenTelemetry shutdown did not complete cleanly; "
            "continuing application shutdown."
        )
    return ShutdownResult(completed=not timed_out, timed_out=timed_out)


def initialize_telemetry(settings: Any) -> TelemetryRuntime:
    global _runtime
    enabled = bool(getattr(settings, "HATCH_OBSERVABILITY_ENABLED", False))
    if not enabled:
        configured = TelemetryRuntime(status="disabled")
    else:
        try:
            configured = _build_enabled_runtime(settings)
        except Exception:
            configured = TelemetryRuntime(status="degraded")
            configured._warn_once(
                "OpenTelemetry initialization failed; continuing with telemetry degraded."
            )
    with _runtime_lock:
        _runtime = configured
    return configured


def _build_enabled_runtime(settings: Any) -> TelemetryRuntime:
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import (
        ConsoleMetricExporter,
        PeriodicExportingMetricReader,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
        SimpleSpanProcessor,
    )

    endpoint = str(settings.HATCH_OTLP_ENDPOINT).strip()
    insecure = endpoint.startswith("http://")
    resource = Resource.create({"service.name": "hatch-backend"})
    tracer_provider = TracerProvider(resource=resource, shutdown_on_exit=False)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=endpoint, insecure=insecure),
            export_timeout_millis=5000,
        )
    )
    readers: list[Any] = [
        PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=endpoint, insecure=insecure),
            export_interval_millis=60_000,
            export_timeout_millis=5000,
        )
    ]
    console_enabled = bool(settings.HATCH_OBSERVABILITY_CONSOLE) and (
        str(settings.LOG_LEVEL).upper() == "DEBUG"
    )
    if console_enabled:
        tracer_provider.add_span_processor(
            SimpleSpanProcessor(ConsoleSpanExporter())
        )
        readers.append(
            PeriodicExportingMetricReader(
                ConsoleMetricExporter(),
                export_interval_millis=60_000,
                export_timeout_millis=5000,
            )
        )
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=readers,
        shutdown_on_exit=False,
    )
    return TelemetryRuntime(
        status="active",
        tracer=tracer_provider.get_tracer("hatch.ai"),
        meter=meter_provider.get_meter("hatch.ai"),
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )
