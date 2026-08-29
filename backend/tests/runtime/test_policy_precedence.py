"""Behavioral contracts for deterministic Control Plane constraint folding."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import BaseModel

from app.runtime.control import (
    AuditLevel,
    BudgetLimits,
    CapturePolicy,
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


def test_lower_precedence_limits_cannot_widen_any_bounded_budget(
    control_plane: ControlPlane,
) -> None:
    """Replacing any bounded minimum with a lower-layer value must fail this."""
    decision = control_plane.evaluate(
        security_policy=PolicyLayer(
            constraints=ConstraintSet(
                budgets=BudgetLimits(
                    max_cost_usd=Decimal("1.25"),
                    max_input_tokens=100,
                    max_output_tokens=200,
                    max_retries=1,
                    max_repairs=2,
                )
            )
        ),
        user_config=PolicyLayer(
            constraints=ConstraintSet(
                budgets=BudgetLimits(
                    max_cost_usd=Decimal("9.99"),
                    max_input_tokens=900,
                    max_output_tokens=800,
                    max_retries=7,
                    max_repairs=6,
                )
            )
        ),
    )

    assert decision.effective_constraints.budgets == BudgetLimits(
        max_cost_usd=Decimal("1.25"),
        max_input_tokens=100,
        max_output_tokens=200,
        max_retries=1,
        max_repairs=2,
    )


def test_lower_precedence_deadline_cannot_extend_earlier_deadline(
    control_plane: ControlPlane,
) -> None:
    """Replacing deadline minima with a lower-layer value must fail this."""
    system_deadline = datetime(2031, 1, 2, tzinfo=UTC)
    user_deadline = datetime(2031, 2, 2, tzinfo=UTC)

    decision = control_plane.evaluate(
        system=PolicyLayer(constraints=ConstraintSet(deadline=system_deadline)),
        user=PolicyLayer(constraints=ConstraintSet(deadline=user_deadline)),
    )

    assert decision.effective_constraints.deadline == system_deadline


def test_lower_precedence_allowlists_cannot_restore_provider_or_capability(
    control_plane: ControlPlane,
) -> None:
    """Replacing either allowlist intersection with assignment must fail this."""
    decision = control_plane.evaluate(
        system=PolicyLayer(
            constraints=ConstraintSet(
                allowed_providers=frozenset({"provider-a"}),
                allowed_capabilities=frozenset({"capability-a"}),
            )
        ),
        user=PolicyLayer(
            constraints=ConstraintSet(
                allowed_providers=frozenset({"provider-a", "provider-b"}),
                allowed_capabilities=frozenset({"capability-a", "capability-b"}),
            )
        ),
    )

    assert decision.effective_constraints.allowed_providers == frozenset({"provider-a"})
    assert decision.effective_constraints.allowed_capabilities == frozenset(
        {"capability-a"}
    )


def test_lower_precedence_can_tighten_audit_and_capture_requirements(
    control_plane: ControlPlane,
) -> None:
    """Dropping audit maximum or capture minimum folding must fail this."""
    decision = control_plane.evaluate(
        system=PolicyLayer(
            constraints=ConstraintSet(
                audit_level=AuditLevel.MINIMAL,
                capture_policy=CapturePolicy.METADATA_ONLY,
            )
        ),
        user=PolicyLayer(
            constraints=ConstraintSet(
                audit_level=AuditLevel.STRICT,
                capture_policy=CapturePolicy.NONE,
            )
        ),
    )

    assert decision.effective_constraints.audit_level is AuditLevel.STRICT
    assert decision.effective_constraints.capture_policy is CapturePolicy.NONE
