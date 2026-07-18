from __future__ import annotations

from types import SimpleNamespace

from app.observability import runtime
from app.observability.runtime import TelemetryRuntime, initialize_telemetry


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
