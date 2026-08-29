"""Public generic capability adapter classes."""

from .artifact import ArtifactCapabilityAdapter
from .llm import (
    LLMCapabilityAdapter,
    StructuredGenerationInput,
    StructuredGenerationOutput,
    register_llm_generate_structured,
)
from .native import CapabilityHandler, NativeCapabilityAdapter

__all__ = [
    "ArtifactCapabilityAdapter",
    "CapabilityHandler",
    "LLMCapabilityAdapter",
    "NativeCapabilityAdapter",
    "StructuredGenerationInput",
    "StructuredGenerationOutput",
    "register_llm_generate_structured",
]
