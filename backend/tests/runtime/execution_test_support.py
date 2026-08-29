"""Synthetic execution-gateway fixtures backed by the real workflow repository."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
import inspect
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.runtime.control import ConstraintSet, ControlPlane, PolicyLayer
from app.runtime.execution import (
    CapabilityDescriptor,
    CapabilityInvocationContext,
    CapabilityRegistry,
    CapabilityResult,
    ExecutionGateway,
    IdempotencyClass,
    SideEffectClass,
)
from app.runtime.workflow import ApprovalManager, ExecutionClaimRecord, WorkflowKernel

from workflow_test_support import start_and_claim


NOW = datetime(2030, 1, 1)


class SyntheticInput(BaseModel):
    """Strict input used to prove untrusted payload validation."""

    model_config = ConfigDict(extra="forbid")

    count: int
    idempotency_key: str | None = None
    sensitive_value: str | None = None


class SyntheticOutput(BaseModel):
    """Typed adapter output used by gateway behavior tests."""

    model_config = ConfigDict(extra="forbid")

    result_ref: str
    count: int


class WrongOutput(BaseModel):
    result_ref: str
    count: str


class RecordingAdapter:
    """Records typed calls while leaving persistence and policy behavior real."""

    def __init__(
        self,
        result: CapabilityResult | None = None,
        *,
        handler: Callable[
            [BaseModel, CapabilityInvocationContext],
            Awaitable[CapabilityResult] | CapabilityResult,
        ]
        | None = None,
    ) -> None:
        self.calls: list[tuple[BaseModel, CapabilityInvocationContext]] = []
        self._result = result or CapabilityResult.success(
            SyntheticOutput(result_ref="synthetic-result", count=7)
        )
        self._handler = handler

    async def invoke(
        self,
        payload: BaseModel,
        context: CapabilityInvocationContext,
    ) -> CapabilityResult:
        self.calls.append((payload, context))
        if self._handler is None:
            return self._result
        value = self._handler(payload, context)
        if inspect.isawaitable(value):
            return await value
        return value  # type: ignore[return-value]


def descriptor(
    capability_id: str = "synthetic.execute",
    *,
    side_effect: SideEffectClass = SideEffectClass.PURE,
    idempotency: IdempotencyClass = IdempotencyClass.IDEMPOTENT,
    timeout: float | None = 1.0,
) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability_id=capability_id,
        version=1,
        input_model=SyntheticInput,
        output_model=SyntheticOutput,
        side_effect_class=side_effect,
        idempotency_class=idempotency,
        required_permissions=(),
        default_timeout_seconds=timeout,
    )


def policy_for(capability_id: str, *, approval_required: bool = False):
    return ControlPlane().evaluate(
        system=PolicyLayer(
            ConstraintSet(
                allowed_capabilities=frozenset({capability_id}),
                approval_required=approval_required,
            )
        )
    )


def denied_policy_for(other_capability: str = "synthetic.other"):
    return ControlPlane().evaluate(
        system=PolicyLayer(
            ConstraintSet(allowed_capabilities=frozenset({other_capability}))
        )
    )


async def gateway_case(
    workflow_runtime,
    adapter: RecordingAdapter,
    capability: CapabilityDescriptor | None = None,
) -> tuple[
    ExecutionGateway,
    WorkflowKernel,
    Any,
    ExecutionClaimRecord,
    CapabilityRegistry,
]:
    kernel, factory = workflow_runtime
    _, claim = await start_and_claim(kernel, now=NOW)
    registry = CapabilityRegistry()
    registration = capability or descriptor()
    registry.register(registration, adapter)
    approvals = ApprovalManager(factory, clock=lambda: NOW)
    gateway = ExecutionGateway(
        registry=registry,
        kernel=kernel,
        approvals=approvals,
    )
    return gateway, kernel, factory, claim, registry
