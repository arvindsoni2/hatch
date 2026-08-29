"""Callable-backed adapter for deterministic native capabilities."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from ..models import (
    CapabilityInvocationContext,
    CapabilityResult,
)

CapabilityHandler = Callable[
    [BaseModel, CapabilityInvocationContext],
    CapabilityResult | BaseModel | Awaitable[CapabilityResult | BaseModel],
]


class NativeCapabilityAdapter:
    """Invokes a supplied native handler and wraps typed model outputs."""

    def __init__(self, handler: CapabilityHandler) -> None:
        if not callable(handler):
            raise TypeError("capability handler must be callable")
        self._handler = handler

    async def invoke(
        self,
        payload: BaseModel,
        context: CapabilityInvocationContext,
    ) -> CapabilityResult:
        value = self._handler(payload, context)
        if inspect.isawaitable(value):
            value = await value
        if isinstance(value, CapabilityResult):
            return value
        if isinstance(value, BaseModel):
            return CapabilityResult.success(value)
        raise TypeError("capability handler returned an invalid typed result")
