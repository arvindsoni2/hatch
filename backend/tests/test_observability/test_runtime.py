from __future__ import annotations

from types import SimpleNamespace

from app.observability import runtime
from app.observability.runtime import (
    TelemetryRuntime,
    initialize_telemetry,
    trace_stage,
    trace_workflow,
)


def _settings(**overrides):
    values = {
        "HATCH_OBSERVABILITY_ENABLED": False,
        "HATCH_OTLP_ENDPOINT": "http://127.0.0.1:4317",
        "HATCH_OBSERVABILITY_CONSOLE": False,
        "LOG_LEVEL": "INFO",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_disabled_runtime_is_constant_time_noop() -> None:
    telemetry = initialize_telemetry(_settings())

    assert telemetry.status == "disabled"
    with telemetry.workflow_span("cv_tailoring", {"hatch.ai.model.id": "local"}) as span:
        span.set_attribute("hatch.ai.validation.state", "passed")
        span.record_exception(RuntimeError("not exported"))
    telemetry.record_model_call(
        workflow="cv_tailoring",
        provider="llamacpp",
        model_id="local",
        duration_ms=12,
    )


def test_runtime_degrades_when_optional_sdk_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(runtime, "_build_enabled_runtime", lambda _settings: (_ for _ in ()).throw(ImportError("missing")))

    telemetry = initialize_telemetry(
        _settings(HATCH_OBSERVABILITY_ENABLED=True)
    )

    assert telemetry.status == "degraded"


def test_telemetry_errors_do_not_change_workflow_result() -> None:
    class BrokenTracer:
        def start_as_current_span(self, *_args, **_kwargs):
            raise RuntimeError("exporter unavailable")

    telemetry = TelemetryRuntime(status="active", tracer=BrokenTracer())

    with telemetry.workflow_span("job_scoring") as span:
        span.set_attribute("hatch.ai.model.id", "local")
        result = {"score": 81}

    assert result == {"score": 81}


def test_metric_instruments_use_stable_names() -> None:
    names: list[str] = []

    class Meter:
        def create_histogram(self, name, **_kwargs):
            names.append(name)
            return SimpleNamespace(record=lambda *_args, **_kwargs: None)

        def create_counter(self, name, **_kwargs):
            names.append(name)
            return SimpleNamespace(add=lambda *_args, **_kwargs: None)

    TelemetryRuntime(status="active", meter=Meter())

    assert names == [
        "hatch.ai.workflow.duration",
        "hatch.ai.model.call.duration",
        "hatch.ai.model.calls",
        "hatch.ai.repair.calls",
        "hatch.ai.validation.failures",
        "hatch.ai.tokens.input",
        "hatch.ai.tokens.output",
        "hatch.ai.workflow.outcomes",
    ]


def test_async_workflow_and_stage_decorators_preserve_result(monkeypatch) -> None:
    events: list[tuple[str, str]] = []

    class RecordingTelemetry:
        def workflow_span(self, workflow):
            events.append(("workflow", workflow))
            return _manager()

        def stage_span(self, workflow, stage):
            events.append(("stage", stage))
            return _manager()

    class _manager:
        def __enter__(self):
            return SimpleNamespace()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(runtime, "get_telemetry", lambda: RecordingTelemetry())

    @trace_workflow("cv_tailoring")
    @trace_stage("cv_tailoring", "generate_initial")
    async def operation():
        return {"unchanged": True}

    import asyncio

    assert asyncio.run(operation()) == {"unchanged": True}
    assert events == [
        ("workflow", "cv_tailoring"),
        ("stage", "generate_initial"),
    ]


def test_controlled_fallback_error_marks_workflow_outcome_failed() -> None:
    outcomes: list[dict[str, object]] = []

    class Instrument:
        def record(self, *_args, **_kwargs) -> None:
            return None

        def add(self, _value, attributes) -> None:
            outcomes.append(attributes)

    class Meter:
        def create_histogram(self, *_args, **_kwargs):
            return Instrument()

        def create_counter(self, *_args, **_kwargs):
            return Instrument()

    class RawSpan:
        def add_event(self, *_args, **_kwargs) -> None:
            return None

        def set_status(self, *_args, **_kwargs) -> None:
            return None

    class Manager:
        def __enter__(self):
            return RawSpan()

        def __exit__(self, *_args):
            return False

    class Tracer:
        def start_as_current_span(self, *_args, **_kwargs):
            return Manager()

    telemetry = TelemetryRuntime(
        status="active",
        tracer=Tracer(),
        meter=Meter(),
    )

    with telemetry.workflow_span("job_discovery_import"):
        telemetry.mark_current_error("classification_failed")
        result = []

    assert result == []
    assert any(
        item.get("hatch.ai.validation.state") == "failed"
        for item in outcomes
    )


def test_current_workflow_uses_active_root_then_restores_default() -> None:
    telemetry = TelemetryRuntime(status="disabled")

    assert telemetry.current_workflow("job_discovery_import") == "job_discovery_import"
    with telemetry.workflow_span("cv_tailoring"):
        assert telemetry.current_workflow("job_discovery_import") == "cv_tailoring"
        with telemetry.workflow_span("cover_letter_generation"):
            assert (
                telemetry.current_workflow("job_discovery_import")
                == "cover_letter_generation"
            )
        assert telemetry.current_workflow("job_discovery_import") == "cv_tailoring"
    assert telemetry.current_workflow("job_discovery_import") == "job_discovery_import"
