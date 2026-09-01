"""Callable-backed adapter for deterministic native capabilities."""

from __future__ import annotations

import asyncio
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
        self._handler_is_async = inspect.iscoroutinefunction(handler) or (
            hasattr(handler, "__call__")
            and inspect.iscoroutinefunction(handler.__call__)
        )

    async def invoke(
        self,
        payload: BaseModel,
        context: CapabilityInvocationContext,
    ) -> CapabilityResult:
        value = (
            self._handler(payload, context)
            if self._handler_is_async
            else await asyncio.to_thread(self._handler, payload, context)
        )
        if inspect.isawaitable(value):
            value = await value
        if isinstance(value, CapabilityResult):
            return value
        if isinstance(value, BaseModel):
            return CapabilityResult.success(value)
        raise TypeError("capability handler returned an invalid typed result")
