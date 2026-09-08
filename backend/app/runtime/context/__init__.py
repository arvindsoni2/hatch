"""Runtime context-plane contracts and resolver services."""

from .models import (
    INITIAL_CONTEXT_CAPABILITIES,
    ContextItem,
    ContextOmission,
    ContextPackage,
    ContextProvider,
    ContextRequirement,
)
from .registry import ContextRegistry


def __getattr__(name: str):
    if name == "ContextResolver":
        from .resolver import ContextResolver

        return ContextResolver
    raise AttributeError(name)


__all__ = [
    "INITIAL_CONTEXT_CAPABILITIES",
    "ContextItem",
    "ContextOmission",
    "ContextPackage",
    "ContextProvider",
    "ContextRegistry",
    "ContextResolver",
    "ContextRequirement",
]
