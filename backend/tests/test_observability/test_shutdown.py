from __future__ import annotations

import threading
import time

from app.observability import runtime
from app.observability.runtime import TelemetryRuntime, shutdown_telemetry


class RecordingProvider:
    def __init__(self, calls: list[str], name: str) -> None:
        self.calls = calls
        self.name = name

    def force_flush(self, **_kwargs) -> bool:
        self.calls.append(f"{self.name}.flush")
        return True

    def shutdown(self, **_kwargs) -> None:
        self.calls.append(f"{self.name}.shutdown")


def test_shutdown_flushes_and_closes_both_providers(monkeypatch) -> None:
    calls: list[str] = []
    telemetry = TelemetryRuntime(
        status="active",
        tracer_provider=RecordingProvider(calls, "traces"),
        meter_provider=RecordingProvider(calls, "metrics"),
    )
    monkeypatch.setattr(runtime, "_runtime", telemetry)

    result = shutdown_telemetry(deadline_seconds=0.5)

    assert result.completed is True
    assert result.timed_out is False
    assert calls == [
        "traces.flush",
        "metrics.flush",
        "traces.shutdown",
        "metrics.shutdown",
    ]


def test_shutdown_contains_provider_errors_and_warns_once(monkeypatch, caplog) -> None:
    class BrokenProvider:
        def force_flush(self, **_kwargs) -> None:
            raise RuntimeError("Bearer private-token")

        def shutdown(self, **_kwargs) -> None:
            raise RuntimeError("still secret")

    telemetry = TelemetryRuntime(
        status="active",
        tracer_provider=BrokenProvider(),
        meter_provider=BrokenProvider(),
    )
    monkeypatch.setattr(runtime, "_runtime", telemetry)

    first = shutdown_telemetry(deadline_seconds=0.5)
    second = shutdown_telemetry(deadline_seconds=0.5)

    assert first.completed is True
    assert second.completed is True
    warnings = [
        record.message
        for record in caplog.records
        if record.levelname == "WARNING"
    ]
    assert warnings == [
        "OpenTelemetry shutdown did not complete cleanly; continuing application shutdown."
    ]
    assert "private-token" not in caplog.text


def test_shutdown_abandons_blocking_provider_on_daemon_thread(monkeypatch) -> None:
    blocker = threading.Event()
    observed: dict[str, bool] = {}

    class BlockingProvider:
        def force_flush(self, **_kwargs) -> None:
            observed["daemon"] = threading.current_thread().daemon
            blocker.wait()

        def shutdown(self, **_kwargs) -> None:
            raise AssertionError("shutdown must not be reached while flush is blocked")

    telemetry = TelemetryRuntime(
        status="active",
        tracer_provider=BlockingProvider(),
    )
    monkeypatch.setattr(runtime, "_runtime", telemetry)
    started = time.monotonic()

    result = shutdown_telemetry(deadline_seconds=0.05)
    elapsed = time.monotonic() - started
    blocker.set()

    assert result.completed is False
    assert result.timed_out is True
    assert elapsed < 0.25
    assert observed == {"daemon": True}


def test_disabled_shutdown_is_immediate(monkeypatch) -> None:
    monkeypatch.setattr(runtime, "_runtime", TelemetryRuntime(status="disabled"))

    assert shutdown_telemetry(deadline_seconds=5.0).completed is True
