"""Optional, privacy-safe Hatch telemetry facade."""
from .runtime import (
    ShutdownResult,
    TelemetryRuntime,
    get_telemetry,
    initialize_telemetry,
    shutdown_telemetry,
)

__all__ = [
    "ShutdownResult",
    "TelemetryRuntime",
    "get_telemetry",
    "initialize_telemetry",
    "shutdown_telemetry",
]
