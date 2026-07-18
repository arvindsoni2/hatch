"""Optional, privacy-safe Hatch telemetry facade."""
from .runtime import (
    ShutdownResult,
    TelemetryRuntime,
    get_telemetry,
    initialize_telemetry,
    instrument_fastapi_app,
    shutdown_telemetry,
)

__all__ = [
    "ShutdownResult",
    "TelemetryRuntime",
    "get_telemetry",
    "initialize_telemetry",
    "instrument_fastapi_app",
    "shutdown_telemetry",
]
