"""Declared context capability registration."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import INITIAL_CONTEXT_CAPABILITIES


@runtime_checkable
class RegisteredContextProvider(Protocol):
    provider_id: str
    capabilities: tuple[str, ...]


class ContextRegistry:
    """Maps every allowed capability to exactly one provider."""

    def __init__(self) -> None:
        self._providers: dict[str, RegisteredContextProvider] = {}

    def register(self, provider: RegisteredContextProvider) -> None:
        if len(set(provider.capabilities)) != len(provider.capabilities):
            raise ValueError("context_capability_duplicate")
        for capability in provider.capabilities:
            if capability not in INITIAL_CONTEXT_CAPABILITIES:
                raise ValueError("context_capability_unknown")
            if capability in self._providers:
                raise ValueError("context_capability_duplicate")
        for capability in provider.capabilities:
            self._providers[capability] = provider

    def provider_for(self, capability: str) -> RegisteredContextProvider | None:
        return self._providers.get(capability)
