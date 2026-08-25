"""Stable runtime contract errors."""


class RuntimeContractError(ValueError):
    """Base class for invalid public runtime contracts."""


class TaskSpecValidationError(RuntimeContractError):
    """Raised when a TaskSpec violates its immutable contract."""


class UnknownRuntimeSliceError(RuntimeContractError):
    """Raised when migration mode is requested for an unregistered slice."""
