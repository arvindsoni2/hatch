"""Trace correlation for application logs without enabling log export."""
from __future__ import annotations

import logging
from typing import Any


class TraceContextFilter(logging.Filter):
    """Ensure correlation fields exist without attaching span attributes."""

    def filter(self, record: Any) -> bool:
        if not getattr(record, "otelTraceID", None):
            record.otelTraceID = "0"
        if not getattr(record, "otelSpanID", None):
            record.otelSpanID = "0"
        return True


def _load_logging_instrumentor() -> Any:
    from opentelemetry.instrumentation.logging import LoggingInstrumentor

    return LoggingInstrumentor


def configure_log_correlation(*, enabled: bool) -> bool:
    """Enable SDK context injection when available, remaining fail-open."""
    correlation_filter = TraceContextFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(correlation_filter)
    if not enabled:
        return False
    try:
        _load_logging_instrumentor()().instrument(set_logging_format=False)
    except Exception:
        return False
    return True
