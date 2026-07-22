from __future__ import annotations

import logging
from types import SimpleNamespace

from app.observability.logging import TraceContextFilter, configure_log_correlation


def test_trace_context_filter_supplies_safe_defaults() -> None:
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "hello",
        (),
        None,
    )

    assert TraceContextFilter().filter(record) is True
    assert record.otelTraceID == "0"
    assert record.otelSpanID == "0"
    assert not hasattr(record, "otelTraceAttributes")


def test_log_correlation_is_optional_and_fail_open(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class Instrumentor:
        def instrument(self, **kwargs) -> None:
            calls.append(kwargs)

    monkeypatch.setattr(
        "app.observability.logging._load_logging_instrumentor",
        lambda: Instrumentor,
    )

    assert configure_log_correlation(enabled=False) is False
    assert configure_log_correlation(enabled=True) is True
    assert calls == [{"set_logging_format": False}]

    monkeypatch.setattr(
        "app.observability.logging._load_logging_instrumentor",
        lambda: (_ for _ in ()).throw(ImportError("missing")),
    )
    assert configure_log_correlation(enabled=True) is False


def test_trace_context_filter_preserves_injected_ids() -> None:
    record = SimpleNamespace(otelTraceID="abc", otelSpanID="def")

    assert TraceContextFilter().filter(record) is True
    assert record.otelTraceID == "abc"
    assert record.otelSpanID == "def"
