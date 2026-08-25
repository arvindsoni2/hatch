"""Immutable correctness contract for one unit of runtime work."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

from .enums import ExecutionStrategy, RiskClass
from .errors import TaskSpecValidationError

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)

_STABLE_NAME = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")


class ContextRequirement(Protocol):
    """Structural boundary implemented by context-plane requirement models."""

    capability: str
    required: bool


@dataclass(frozen=True)
class ModelCapabilityRequirements:
    """Mandatory model capabilities, separate from operational preferences."""

    required_capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvaluationPolicy:
    """Bound evaluation work for a task attempt."""

    max_evaluations: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.max_evaluations, bool) or self.max_evaluations < 0:
            raise ValueError("max_evaluations must be a non-negative integer")


@dataclass(frozen=True)
class WorkflowPolicy:
    """Bound durable attempts for a task."""

    max_attempts: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.max_attempts, bool) or self.max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")


@dataclass(frozen=True)
class TaskSpec(Generic[InputT, OutputT]):
    """Versioned, immutable correctness contract for runtime execution."""

    task_id: str
    version: int
    input_model: type[InputT]
    output_model: type[OutputT]
    context_requirements: tuple[ContextRequirement, ...]
    model_requirements: ModelCapabilityRequirements
    risk_class: RiskClass
    validators: tuple[str, ...]
    evaluation_policy: EvaluationPolicy
    execution_strategy: ExecutionStrategy
    workflow_policy: WorkflowPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, str) or not _STABLE_NAME.fullmatch(self.task_id):
            raise TaskSpecValidationError("task_id must be a stable lowercase identifier")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise TaskSpecValidationError("version must be a positive integer")
        self._validate_model("input_model", self.input_model)
        self._validate_model("output_model", self.output_model)
        if not self.validators:
            raise TaskSpecValidationError("at least one validator is required")
        if len(set(self.validators)) != len(self.validators):
            raise TaskSpecValidationError("validators must be unique")
        if any(
            not isinstance(validator, str) or not _STABLE_NAME.fullmatch(validator)
            for validator in self.validators
        ):
            raise TaskSpecValidationError("validator names must be stable lowercase identifiers")

    @staticmethod
    def _validate_model(field_name: str, model: object) -> None:
        if not isinstance(model, type) or not issubclass(model, BaseModel):
            raise TaskSpecValidationError(
                f"{field_name} must be a pydantic BaseModel subclass"
            )
