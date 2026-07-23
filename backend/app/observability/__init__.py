"""Optional, privacy-safe Hatch telemetry facade."""

from .runtime import (
    ShutdownResult,
    TelemetryRuntime,
    TraceContextToken,
    get_telemetry,
    initialize_telemetry,
    instrument_fastapi_app,
    shutdown_telemetry,
    trace_stage,
    trace_workflow,
)

__all__ = [
    "ShutdownResult",
    "TelemetryRuntime",
    "TraceContextToken",
    "get_telemetry",
    "initialize_telemetry",
    "instrument_fastapi_app",
    "shutdown_telemetry",
    "trace_stage",
    "trace_workflow",
]
