"""Public typed Execution Gateway contracts."""

from .gateway import ExecutionGateway
from .models import (
    CapabilityDescriptor,
    CapabilityInvocationContext,
    CapabilityResult,
    ExecutionTelemetry,
    IdempotencyClass,
    SideEffectClass,
)
from .registry import CapabilityAdapter, CapabilityRegistration, CapabilityRegistry

__all__ = [
    "CapabilityAdapter",
    "CapabilityDescriptor",
    "CapabilityInvocationContext",
    "CapabilityRegistration",
    "CapabilityRegistry",
    "CapabilityResult",
    "ExecutionGateway",
    "ExecutionTelemetry",
    "IdempotencyClass",
    "SideEffectClass",
]
