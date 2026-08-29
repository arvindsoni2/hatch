"""Behavioral contracts for deterministic Control Plane constraint folding."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.runtime.control import (
    BudgetLimits,
    ConstraintSet,
    ControlPlane,
    PolicyLayer,
)
from app.runtime.contracts import (
    EvaluationPolicy,
    ExecutionStrategy,
    ModelCapabilityRequirements,
    RiskClass,
    TaskSpec,
    WorkflowPolicy,
)


class _Input(BaseModel):
    value: str


class _Output(BaseModel):
    value: str


def _task_spec(*, max_attempts: int = 3, max_evaluations: int = 2) -> TaskSpec[_Input, _Output]:
    return TaskSpec(
        task_id="control.precedence",
        version=1,
        input_model=_Input,
        output_model=_Output,
        context_requirements=(),
        model_requirements=ModelCapabilityRequirements(),
        risk_class=RiskClass.LOW,
        validators=("control.validator",),
        evaluation_policy=EvaluationPolicy(max_evaluations=max_evaluations),
        execution_strategy=ExecutionStrategy.SINGLE_PASS,
        workflow_policy=WorkflowPolicy(max_attempts=max_attempts),
    )


@pytest.fixture
def control_plane() -> ControlPlane:
    return ControlPlane()


def test_user_config_cannot_weaken_system_egress_denial(
    control_plane: ControlPlane,
) -> None:
    """Removing the AND fold for egress must make this test fail."""
    decision = control_plane.evaluate(
        system=PolicyLayer(constraints=ConstraintSet(data_egress=False)),
        user=PolicyLayer(constraints=ConstraintSet(data_egress=True)),
    )

    assert decision.effective_constraints.data_egress is False
    assert "system.data_egress_denied" in decision.reason_codes


def test_lower_precedence_budgets_can_only_reduce_task_budget(
    control_plane: ControlPlane,
) -> None:
    """Replacing budget minima with a lower-layer value must make this fail."""
    decision = control_plane.evaluate(
        task_spec=_task_spec(max_attempts=3, max_evaluations=2),
        security_policy=PolicyLayer(
            constraints=ConstraintSet(budgets=BudgetLimits(max_attempts=8, max_evaluations=9))
        ),
        workflow_policy=PolicyLayer(
            constraints=ConstraintSet(budgets=BudgetLimits(max_attempts=2, max_evaluations=1))
        ),
        user_config=PolicyLayer(
            constraints=ConstraintSet(budgets=BudgetLimits(max_attempts=7, max_evaluations=7))
        ),
        routing_preferences=PolicyLayer(
            constraints=ConstraintSet(budgets=BudgetLimits(max_attempts=6, max_evaluations=6))
        ),
    )

    assert decision.effective_constraints.budgets == BudgetLimits(
        max_attempts=2,
        max_evaluations=1,
    )


def test_lower_precedence_model_allowlist_cannot_restore_denied_model(
    control_plane: ControlPlane,
) -> None:
    """Replacing allowlist intersection with assignment must make this fail."""
    decision = control_plane.evaluate(
        system=PolicyLayer(
            constraints=ConstraintSet(allowed_models=frozenset({"model-a"}))
        ),
        security_policy=PolicyLayer(
            constraints=ConstraintSet(allowed_models=frozenset({"model-a", "model-b"}))
        ),
    )

    assert decision.effective_constraints.allowed_models == frozenset({"model-a"})


def test_constraints_snapshot_mutable_allowlists_as_immutable_values() -> None:
    """Removing defensive set normalization must make this test fail."""
    supplied_models = {"model-a"}

    constraints = ConstraintSet(allowed_models=supplied_models)
    supplied_models.add("model-b")

    assert constraints.allowed_models == frozenset({"model-a"})
