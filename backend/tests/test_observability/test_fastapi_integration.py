from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import main
from app.observability import runtime
from app.observability.runtime import TelemetryRuntime
from app.routers import jobs


def test_create_app_initializes_and_instruments_telemetry_once(monkeypatch) -> None:
    telemetry = TelemetryRuntime(status="active")
    initialized: list[object] = []
    instrumented: list[tuple[object, object]] = []
    monkeypatch.setattr(
        main,
        "initialize_telemetry",
        lambda settings: initialized.append(settings) or telemetry,
        raising=False,
    )
    monkeypatch.setattr(
        main,
        "instrument_fastapi_app",
        lambda app, configured: instrumented.append((app, configured)) or True,
        raising=False,
    )

    built = main.create_app()

    assert initialized == [main.settings]
    assert instrumented == [(built, telemetry)]


def test_fastapi_instrumentation_uses_explicit_providers_and_no_headers(
    monkeypatch,
) -> None:
    calls: list[tuple[object, dict[str, object]]] = []

    class Instrumentor:
        @classmethod
        def instrument_app(cls, app, **kwargs) -> None:
            calls.append((app, kwargs))

    monkeypatch.setattr(
        runtime,
        "_load_fastapi_instrumentor",
        lambda: Instrumentor,
    )
    monkeypatch.setattr(
        runtime,
        "configure_log_correlation",
        lambda *, enabled: enabled,
    )
    app = object()
    tracer_provider = object()
    meter_provider = object()
    telemetry = TelemetryRuntime(
        status="active",
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )

    assert runtime.instrument_fastapi_app(app, telemetry) is True
    assert calls == [
        (
            app,
            {
                "tracer_provider": tracer_provider,
                "meter_provider": meter_provider,
                "exclude_spans": ["receive", "send"],
            },
        )
    ]


def test_fastapi_instrumentation_failure_is_degraded_and_fail_open(
    monkeypatch,
) -> None:
    telemetry = TelemetryRuntime(status="active")
    monkeypatch.setattr(
        runtime,
        "_load_fastapi_instrumentor",
        lambda: (_ for _ in ()).throw(ImportError("missing")),
    )

    assert runtime.instrument_fastapi_app(object(), telemetry) is False
    assert telemetry.status == "degraded"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["disabled", "active", "degraded"])
async def test_health_exposes_only_telemetry_status(monkeypatch, status) -> None:
    monkeypatch.setattr(
        jobs,
        "get_telemetry",
        lambda: SimpleNamespace(
            status=status,
            endpoint="http://user:secret@collector:4317",
        ),
        raising=False,
    )

    response = await jobs.health_check()

    assert response["telemetry"] == {"status": status}
    assert "endpoint" not in str(response)
