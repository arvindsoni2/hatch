"""Public entry point for the product-independent Hatch runtime."""

from .contracts import TaskSpec
from .migration import RuntimeMode, resolve_runtime_mode

__all__ = ["RuntimeMode", "TaskSpec", "resolve_runtime_mode"]
