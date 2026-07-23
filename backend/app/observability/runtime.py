"""Optional OpenTelemetry runtime behind a dependency-free Hatch facade."""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from collections.abc import Mapping
from typing import Any, Literal

from .attributes import (
    COACH_GATE_CODE,
    FAILED_GATE_CODES,
    MODEL_ID,
    PROVIDER_TYPE,
    VALIDATION_STATE,
    WORKFLOW_NAME,
    COACH_OUTCOME,
    COACH_STAGE,
    sanitize_attributes,
    sanitize_metric_attributes,
)
from .coach import (
    COACH_ASYNC_JOB_OUTCOMES,
    COACH_EVALUATION_OUTCOMES,
    COACH_MODEL_ANSWER_OUTCOMES,
    COACH_OUTCOME_METRICS,
    COACH_QUESTION_GENERATION_COUNT,
    COACH_REPORT_OUTCOMES,
    COACH_RUBRIC_OUTCOMES,
    COACH_STAGE_DURATION,
    COACH_STAGE_OUTCOMES,
    metric_stage_name,
)
from .logging import configure_log_correlation

logger = logging.getLogger(__name__)
TelemetryStatus = Literal["disabled", "active", "degraded"]
_ALLOWED_EVENT_NAMES = frozenset(
    {
        "model_error",
        "coach_gate",
        "validation_failure",
        "workflow_error",
    }
)


class SafeSpan:
    """Best-effort span adapter that never raises into business logic."""

    def __init__(self, span: Any = None, parent: SafeSpan | None = None) -> None:
        self._span = span
        self._parent = parent
        self._failed = False
        self._attributes: dict[str, Any] = {}

    @property
    def failed(self) -> bool:
        return self._failed

    def set_attribute(self, key: str, value: Any) -> None:
        attributes = sanitize_attributes({key: value})
        if key not in attributes:
            return
        self._attributes[key] = attributes[key]
        if self._span is None:
            return
        try:
            self._span.set_attribute(key, attributes[key])
        except Exception:
            return

    def get_attribute(self, key: str, default: Any = None) -> Any:
        """Return a sanitized value recorded through this adapter."""
        return self._attributes.get(key, default)

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        if self._span is None:
            return
        safe_name = (
            name
            if isinstance(name, str) and name in _ALLOWED_EVENT_NAMES
            else "telemetry_event"
        )
        try:
            self._span.add_event(safe_name, sanitize_attributes(attributes))
        except Exception:
            return

    def record_exception(self, exception: BaseException) -> None:
        # OpenTelemetry's default exception event contains the message and a
        # stack trace. Both can contain prompts, document content, secrets, or
        # local paths, so Hatch deliberately records only the exception type
        # through the sanitized status code in ``set_error``.
        del exception

    def set_error(self, code: str) -> None:
        self._failed = True
        if self._parent is not None:
            self._parent.set_error(code)
        if self._span is None:
            return
        try:
            from opentelemetry.trace.status import Status, StatusCode

            self._span.set_status(Status(StatusCode.ERROR, code[:64]))
        except Exception:
            return


_current_span: ContextVar[SafeSpan | None] = ContextVar(
    "hatch_current_telemetry_span",
    default=None,
)
_current_workflow: ContextVar[str | None] = ContextVar(
    "hatch_current_telemetry_workflow",
    default=None,
)


@dataclass(frozen=True)
class ShutdownResult:
    completed: bool
    timed_out: bool


@dataclass(frozen=True)
class TraceContextToken:
    """Immutable, content-free request trace context for a later span link."""

    span_context: Any = None


@dataclass(frozen=True)
class _BackgroundTraceState:
    token: TraceContextToken
    attributes: tuple[tuple[str, Any], ...]


_background_trace_state: ContextVar[_BackgroundTraceState | None] = ContextVar(
    "hatch_background_trace_state",
    default=None,
)


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
        self._coach_stage_duration = self._histogram(COACH_STAGE_DURATION)
        self._coach_stage_outcomes = self._counter(COACH_STAGE_OUTCOMES)
        self._coach_question_generation_count = self._counter(
            COACH_QUESTION_GENERATION_COUNT
        )
        self._coach_outcome_instruments = {
            "model_answer": self._counter(COACH_MODEL_ANSWER_OUTCOMES),
            "evaluation": self._counter(COACH_EVALUATION_OUTCOMES),
            "rubric": self._counter(COACH_RUBRIC_OUTCOMES),
            "report": self._counter(COACH_REPORT_OUTCOMES),
            "async_job": self._counter(COACH_ASYNC_JOB_OUTCOMES),
        }

    def _histogram(self, name: str) -> Any:
        if self.status != "active" or self.meter is None:
            return None
        try:
            return self.meter.create_histogram(name, unit="ms")
        except Exception:
            return None

    def _counter(self, name: str) -> Any:
        if self.status != "active" or self.meter is None:
            return None
        try:
            return self.meter.create_counter(name)
        except Exception:
            return None

    @contextmanager
    def _span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
        *,
        link_context: Any = None,
    ):
        if self.status != "active" or self.tracer is None:
            yield SafeSpan()
            return
        try:
            start_options: dict[str, Any] = {
                "attributes": sanitize_attributes(attributes),
            }
            if link_context is not None:
                from opentelemetry.context import Context
                from opentelemetry.trace import Link

                start_options["context"] = Context()
                start_options["links"] = (Link(link_context),)
            manager = self.tracer.start_as_current_span(
                name,
                **start_options,
            )
            raw_span = manager.__enter__()
        except Exception:
            yield SafeSpan()
            return
        span = SafeSpan(raw_span, parent=_current_span.get())
        token = _current_span.set(span)
        try:
            yield span
        except BaseException as exc:
            span.record_exception(exc)
            span.set_error(type(exc).__name__)
            raise
        finally:
            _current_span.reset(token)
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
        background = _background_trace_state.get()
        background_attributes = (
            dict(background.attributes) if background is not None else {}
        )
        safe_attributes = {
            WORKFLOW_NAME: workflow,
            **background_attributes,
            **(attributes or {}),
        }
        link_context = background.token.span_context if background is not None else None
        outcome = "completed"
        workflow_token = _current_workflow.set(workflow)
        try:
            with self._span(
                f"hatch.ai.workflow.{workflow}",
                safe_attributes,
                link_context=link_context,
            ) as span:
                yield span
                if span.failed:
                    outcome = "failed"
        except BaseException:
            outcome = "failed"
            raise
        finally:
            _current_workflow.reset(workflow_token)
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

    @contextmanager
    def coach_stage_span(
        self,
        name: str,
        attributes: Mapping[str, Any] | None = None,
    ):
        """Observe one exact Coach stage and its bounded operational outcome."""
        started = time.monotonic()
        supplied = dict(attributes or {})
        outcome = supplied.get(COACH_OUTCOME, "completed")
        if not isinstance(outcome, str):
            outcome = "completed"
        metric_attributes = {
            **supplied,
            COACH_STAGE: metric_stage_name(name),
            COACH_OUTCOME: outcome,
        }
        try:
            with self._span(name, metric_attributes) as span:
                yield span
                metric_attributes[COACH_OUTCOME] = span.get_attribute(
                    COACH_OUTCOME,
                    outcome,
                )
        except BaseException:
            metric_attributes[COACH_OUTCOME] = "failed"
            raise
        finally:
            duration_ms = (time.monotonic() - started) * 1000
            self._record(
                self._coach_stage_duration,
                duration_ms,
                metric_attributes,
            )
            self._add(
                self._coach_stage_outcomes,
                1,
                metric_attributes,
            )

    @staticmethod
    def _record(instrument: Any, value: float, attributes: dict[str, Any]) -> None:
        if instrument is None:
            return
        try:
            instrument.record(value, sanitize_metric_attributes(attributes))
        except Exception:
            return

    @staticmethod
    def _add(instrument: Any, value: int, attributes: dict[str, Any]) -> None:
        if instrument is None:
            return
        try:
            instrument.add(value, sanitize_metric_attributes(attributes))
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
        outcome: str = "completed",
    ) -> None:
        attributes = {
            WORKFLOW_NAME: workflow,
            PROVIDER_TYPE: provider,
            MODEL_ID: model_id,
            VALIDATION_STATE: outcome,
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

    def record_coach_question_count(
        self,
        count: int,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        """Record a non-negative number of generated Coach questions."""
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            return
        self._add(
            self._coach_question_generation_count,
            count,
            dict(attributes or {}),
        )

    def record_coach_outcome(
        self,
        family: str,
        outcome: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        """Increment one allowlisted Coach outcome family."""
        if family not in COACH_OUTCOME_METRICS:
            return
        instrument = self._coach_outcome_instruments.get(family)
        self._add(
            instrument,
            1,
            {**dict(attributes or {}), COACH_OUTCOME: outcome},
        )

    def record_coach_diagnostic(
        self,
        family: str | None,
        outcome: str,
        gate_codes: list[str] | tuple[str, ...] = (),
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        """Annotate the current Coach stage and record its bounded outcome."""
        span = _current_span.get()
        if span is not None:
            span.set_attribute(COACH_OUTCOME, outcome)
            for gate_code in tuple(gate_codes)[:32]:
                span.add_event("coach_gate", {COACH_GATE_CODE: gate_code})
        if family is not None:
            self.record_coach_outcome(family, outcome, attributes)

    def capture_trace_context(self) -> TraceContextToken:
        """Capture only a valid current SpanContext, never the request span."""
        if self.status != "active":
            return TraceContextToken()
        try:
            from opentelemetry.trace import get_current_span

            span_context = get_current_span().get_span_context()
            if not span_context.is_valid:
                return TraceContextToken()
            return TraceContextToken(span_context=span_context)
        except Exception:
            return TraceContextToken()

    @contextmanager
    def use_background_trace_context(
        self,
        token: TraceContextToken,
        attributes: Mapping[str, Any] | None = None,
    ):
        """Make one immutable link and safe root attributes available to a job."""
        span_context = token.span_context
        try:
            valid = bool(span_context is not None and span_context.is_valid)
        except Exception:
            valid = False
        state = _BackgroundTraceState(
            token=token if valid else TraceContextToken(),
            attributes=tuple(sanitize_attributes(attributes).items()),
        )
        context_token = _background_trace_state.set(state)
        try:
            yield
        finally:
            _background_trace_state.reset(context_token)

    def mark_current_error(
        self,
        code: str,
        event_name: str = "workflow_error",
    ) -> None:
        span = _current_span.get()
        if span is None:
            return
        span.add_event(event_name)
        span.set_error(code)

    @staticmethod
    def current_workflow(default: str) -> str:
        """Return the active Hatch workflow, or a safe caller-provided default."""
        return _current_workflow.get() or default

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


def trace_workflow(
    workflow: str,
    *,
    attributes: Mapping[str, Any] | None = None,
    stage: str | None = None,
    nested_stage_only: bool = False,
):
    """Decorate an async workflow with the current fail-open runtime."""

    static_attributes = dict(attributes or {})

    def decorate(function):
        @wraps(function)
        async def wrapped(*args, **kwargs):
            telemetry = get_telemetry()
            if (
                nested_stage_only
                and stage is not None
                and telemetry.current_workflow("") == workflow
            ):
                with telemetry.coach_stage_span(stage):
                    return await function(*args, **kwargs)
            manager = (
                telemetry.workflow_span(workflow, static_attributes)
                if static_attributes
                else telemetry.workflow_span(workflow)
            )
            with manager:
                if stage is not None:
                    with telemetry.coach_stage_span(stage):
                        return await function(*args, **kwargs)
                return await function(*args, **kwargs)

        wrapped.__hatch_workflow__ = workflow
        wrapped.__hatch_workflow_attributes__ = static_attributes
        wrapped.__hatch_stage__ = stage
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
        tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
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
