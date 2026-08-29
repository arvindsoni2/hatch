"""Typed, privacy-safe contracts for capability execution."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from ..contracts import ExecutionResultCode
from ..control import BudgetLimits

_STABLE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")


class SideEffectClass(str, Enum):
    PURE = "pure"
    READ_ONLY_EXTERNAL = "read_only_external"
    PREPARE_SIDE_EFFECT = "prepare_side_effect"
    COMMIT_SIDE_EFFECT = "commit_side_effect"
    ARTIFACT_GENERATION = "artifact_generation"


class IdempotencyClass(str, Enum):
    IDEMPOTENT = "idempotent"
    IDEMPOTENT_WITH_KEY = "idempotent_with_key"
    CHECK_BEFORE_RETRY = "check_before_retry"
    NON_RETRYABLE_SIDE_EFFECT = "non_retryable_side_effect"


class CapabilityDescriptor(BaseModel):
    """Immutable schema and execution semantics for one registered capability."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    capability_id: str
    version: int
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    side_effect_class: SideEffectClass
    idempotency_class: IdempotencyClass
    required_permissions: tuple[str, ...] = ()
    default_timeout_seconds: float | None = None
    requires_data_egress: bool = False
    uses_model_routing: bool = False
    uses_provider_routing: bool = False

    @field_validator("capability_id")
    @classmethod
    def _capability_id_is_stable(cls, value: str) -> str:
        if len(value) > 128 or _STABLE_IDENTIFIER.fullmatch(value) is None:
            raise ValueError("capability_id must be a bounded stable identifier")
        return value

    @field_validator("version")
    @classmethod
    def _version_is_positive(cls, value: int) -> int:
        if isinstance(value, bool) or value < 1:
            raise ValueError("capability version must be positive")
        return value

    @field_validator("required_permissions")
    @classmethod
    def _permissions_are_stable(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(
            len(value) > 128 or _STABLE_IDENTIFIER.fullmatch(value) is None
            for value in values
        ):
            raise ValueError("required permissions must be bounded stable identifiers")
        return values

    @field_validator("default_timeout_seconds")
    @classmethod
    def _timeout_is_positive(cls, value: float | None) -> float | None:
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError("default timeout must be positive")
        return value


class CapabilityResult(BaseModel):
    """Typed adapter result; raw exception text is never part of this contract."""

    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
        strict=True,
    )

    code: ExecutionResultCode
    output: Any = None
    reason_code: str = "success"
    retry_allowed: bool = False
    reconciliation_reference: str | None = None

    @field_validator("reason_code")
    @classmethod
    def _reason_is_stable(cls, value: str) -> str:
        if len(value) > 128 or _STABLE_IDENTIFIER.fullmatch(value) is None:
            raise ValueError("reason_code must be a bounded stable identifier")
        return value

    @field_validator("reconciliation_reference")
    @classmethod
    def _reference_is_bounded(cls, value: str | None) -> str | None:
        if value is not None and (not value or len(value) > 512):
            raise ValueError("reconciliation reference must be bounded")
        return value

    @model_validator(mode="after")
    def _success_requires_output(self) -> "CapabilityResult":
        if self.code is ExecutionResultCode.SUCCESS and self.output is None:
            raise ValueError("successful capability results require output")
        return self

    @classmethod
    def success(cls, output: BaseModel) -> "CapabilityResult":
        return cls(code=ExecutionResultCode.SUCCESS, output=output)


@dataclass(frozen=True)
class CapabilityInvocationContext:
    """Bounded invocation controls passed to an adapter, including replay key."""

    deadline: datetime | None
    budgets: BudgetLimits
    idempotency_key: str | None
    data_egress: bool
    allowed_models: frozenset[str] | None
    allowed_providers: frozenset[str] | None
    model_id: str | None
    provider: str | None


@dataclass(frozen=True)
class ExecutionTelemetry:
    """Content-free post-persistence telemetry payload."""

    capability_id: str
    capability_version: int
    result_code: ExecutionResultCode
    reason_code: str
    retry_allowed: bool
    latency_ms: int
    persisted: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "capability_id": self.capability_id,
            "capability_version": self.capability_version,
            "result_code": self.result_code.value,
            "reason_code": self.reason_code,
            "retry_allowed": self.retry_allowed,
            "latency_ms": self.latency_ms,
            "persisted": self.persisted,
        }
