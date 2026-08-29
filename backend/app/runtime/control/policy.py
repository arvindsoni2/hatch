"""Deterministic precedence folding for runtime authorization constraints."""

from __future__ import annotations

from typing import TypeAlias

from ..contracts import TaskSpec
from .budgets import BudgetLimits
from .models import (
    ConstraintSet,
    EffectiveConstraints,
    PolicyDecision,
    PolicyLayer,
    RoutingPreferences,
)

LayerInput: TypeAlias = PolicyLayer | ConstraintSet | None


class ControlPlane:
    """Folds immutable policy inputs in fixed order without widening constraints."""

    def evaluate(
        self,
        task_spec: TaskSpec | None = None,
        security_policy: LayerInput = None,
        workflow_policy: LayerInput = None,
        user_config: LayerInput = None,
        routing_preferences: RoutingPreferences | LayerInput = None,
        *,
        system: LayerInput = None,
        task: TaskSpec | None = None,
        user: LayerInput = None,
        routing: RoutingPreferences | LayerInput = None,
    ) -> PolicyDecision:
        """Evaluate system through routing inputs in the approved precedence order.

        Keyword aliases retain compatibility with the compact behavioral examples
        while canonical argument names remain the public integration contract.
        """
        if task_spec is not None and task is not None:
            raise ValueError("provide only one of task_spec or task")
        if user_config is not None and user is not None:
            raise ValueError("provide only one of user_config or user")
        if routing_preferences is not None and routing is not None:
            raise ValueError("provide only one of routing_preferences or routing")

        resolved_task = task_spec if task_spec is not None else task
        resolved_user = user_config if user_config is not None else user
        resolved_routing = (
            routing_preferences if routing_preferences is not None else routing
        )
        routing_input = _as_routing_preferences(resolved_routing)
        layers = (
            ("system", _as_layer(system)),
            ("task", _task_constraints(resolved_task)),
            ("security", _as_layer(security_policy)),
            ("workflow", _as_layer(workflow_policy)),
            ("user", _as_layer(resolved_user)),
            ("routing", routing_input.constraints),
        )

        effective = EffectiveConstraints()
        reasons: list[str] = []
        for source, constraints in layers:
            effective = _tighten(effective, constraints)
            if constraints.data_egress is False:
                _add_reason(reasons, f"{source}.data_egress_denied")

        effective = EffectiveConstraints(
            data_egress=effective.data_egress,
            allowed_models=effective.allowed_models,
            required_model_capabilities=effective.required_model_capabilities,
            budgets=effective.budgets,
            forced_model=routing_input.force_model,
        )
        _validate_forced_model(effective, routing_input, reasons)
        return PolicyDecision(
            decision="DENY" if reasons_for_denial(reasons) else "ALLOW",
            reason_codes=tuple(reasons),
            effective_constraints=effective,
        )


def _as_layer(value: LayerInput) -> ConstraintSet:
    if value is None:
        return ConstraintSet()
    if isinstance(value, PolicyLayer):
        return value.constraints
    if isinstance(value, ConstraintSet):
        return value
    raise TypeError("policy layers must be PolicyLayer, ConstraintSet, or None")


def _as_routing_preferences(
    value: RoutingPreferences | LayerInput,
) -> RoutingPreferences:
    if value is None:
        return RoutingPreferences()
    if isinstance(value, RoutingPreferences):
        return value
    return RoutingPreferences(constraints=_as_layer(value))


def _task_constraints(task_spec: TaskSpec | None) -> ConstraintSet:
    if task_spec is None:
        return ConstraintSet()
    return ConstraintSet(
        required_model_capabilities=frozenset(
            task_spec.model_requirements.required_capabilities
        ),
        budgets=BudgetLimits(
            max_attempts=task_spec.workflow_policy.max_attempts,
            max_evaluations=task_spec.evaluation_policy.max_evaluations,
        ),
    )


def _tighten(
    effective: EffectiveConstraints,
    lower_precedence: ConstraintSet,
) -> EffectiveConstraints:
    return EffectiveConstraints(
        data_egress=(
            effective.data_egress
            if lower_precedence.data_egress is None
            else effective.data_egress and lower_precedence.data_egress
        ),
        allowed_models=_intersect_allowlists(
            effective.allowed_models,
            lower_precedence.allowed_models,
        ),
        required_model_capabilities=(
            effective.required_model_capabilities
            | lower_precedence.required_model_capabilities
        ),
        budgets=effective.budgets.tighten(lower_precedence.budgets),
    )


def _intersect_allowlists(
    existing: frozenset[str] | None,
    additional: frozenset[str] | None,
) -> frozenset[str] | None:
    if existing is None:
        return additional
    if additional is None:
        return existing
    return existing & additional


def _validate_forced_model(
    effective: EffectiveConstraints,
    routing: RoutingPreferences,
    reasons: list[str],
) -> None:
    forced_model = routing.force_model
    if forced_model is None:
        return
    if (
        effective.allowed_models is not None
        and forced_model not in effective.allowed_models
    ):
        _add_reason(reasons, "model.force_not_allowed")
    missing_capabilities = (
        effective.required_model_capabilities - routing.model_capabilities
    )
    for capability in sorted(missing_capabilities):
        _add_reason(reasons, f"model.{capability}_required")


def _add_reason(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def reasons_for_denial(reasons: list[str]) -> bool:
    """Only model authorization failures deny a model selection at this layer."""
    return any(reason.startswith("model.") for reason in reasons)
