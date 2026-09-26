"""Contract tests for immutable runtime task specifications."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from pydantic import BaseModel

from app.runtime.contracts import (
    ApprovalId,
    EvaluationPolicy,
    EventId,
    ExecutionId,
    ExecutionResultCode,
    ExecutionStrategy,
    ModelCapabilityRequirements,
    OutboxEntryId,
    PolicyDecisionId,
    RiskClass,
    RoutingDecisionId,
    TaskAttemptId,
    TaskSpec,
    TaskSpecValidationError,
    WorkflowPolicy,
    WorkflowRunId,
    WorkflowStepId,
)


class EchoInput(BaseModel):
    value: str


class EchoOutput(BaseModel):
    value: str


def _valid_spec(**overrides: object) -> TaskSpec[EchoInput, EchoOutput]:
    values: dict[str, object] = {
        "task_id": "test.echo",
        "version": 1,
        "input_model": EchoInput,
        "output_model": EchoOutput,
        "context_requirements": (),
        "model_requirements": ModelCapabilityRequirements(),
        "risk_class": RiskClass.LOW,
        "validators": ("echo.schema.v1",),
        "evaluation_policy": EvaluationPolicy(max_evaluations=0),
        "execution_strategy": ExecutionStrategy.SINGLE_PASS,
        "workflow_policy": WorkflowPolicy(max_attempts=1),
    }
    values.update(overrides)
    return TaskSpec(**values)  # type: ignore[arg-type,return-value]


def test_task_spec_is_frozen_and_versioned() -> None:
    spec = _valid_spec()

    assert (spec.task_id, spec.version) == ("test.echo", 1)
    with pytest.raises(FrozenInstanceError):
        spec.version = 2  # type: ignore[misc]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"task_id": ""}, "task_id"),
        ({"task_id": "Unsafe Task"}, "task_id"),
        ({"version": 0}, "version"),
        ({"validators": ()}, "validator"),
        ({"validators": ("echo.schema.v1", "echo.schema.v1")}, "unique"),
        ({"validators": ("unsafe validator",)}, "validator"),
    ],
)
def test_task_spec_rejects_invalid_identity_and_validator_contracts(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(TaskSpecValidationError, match=message):
        _valid_spec(**overrides)


def test_task_spec_requires_pydantic_input_and_output_models() -> None:
    class NotAModel:
        pass

    with pytest.raises(TaskSpecValidationError, match="input_model"):
        _valid_spec(input_model=NotAModel)
    with pytest.raises(TaskSpecValidationError, match="output_model"):
        _valid_spec(output_model=NotAModel)


@pytest.mark.parametrize(
    "policy",
    [
        lambda: EvaluationPolicy(max_evaluations=-1),
        lambda: WorkflowPolicy(max_attempts=0),
    ],
)
def test_bounded_policies_reject_negative_or_zero_limits(policy) -> None:
    with pytest.raises(ValueError):
        policy()


def test_public_enums_use_the_canonical_persisted_values() -> None:
    assert {member.value for member in ExecutionStrategy} == {
        "single_pass",
        "validate_and_repair",
        "fallback_on_failure",
    }
    assert {member.value for member in ExecutionResultCode} == {
        "success",
        "validation_failure",
        "policy_denied",
        "timeout",
        "cancelled",
        "transient_failure",
        "permanent_failure",
        "outcome_unknown",
    }


def test_semantic_ids_remain_string_compatible_without_becoming_interchangeable_types() -> None:
    constructors = (
        WorkflowRunId,
        WorkflowStepId,
        TaskAttemptId,
        ExecutionId,
        PolicyDecisionId,
        RoutingDecisionId,
        EventId,
        OutboxEntryId,
        ApprovalId,
    )
    assert [constructor("synthetic-id") for constructor in constructors] == [
        "synthetic-id"
    ] * len(constructors)
