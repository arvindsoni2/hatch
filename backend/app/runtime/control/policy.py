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
            allowed_providers=effective.allowed_providers,
            allowed_models=effective.allowed_models,
            allowed_capabilities=effective.allowed_capabilities,
            required_model_capabilities=effective.required_model_capabilities,
            budgets=effective.budgets,
            deadline=effective.deadline,
            approval_required=effective.approval_required,
            audit_level=effective.audit_level,
            capture_policy=effective.capture_policy,
            forced_model=routing_input.force_model,
        )
        denied = _validate_empty_allowlists(effective, reasons)
        denied = _validate_forced_model(effective, routing_input, reasons) or denied
        if effective.approval_required:
            _add_reason(reasons, "approval.required")
        return PolicyDecision(
            decision=(
                "DENY"
                if denied
                else "REQUIRE_APPROVAL"
                if effective.approval_required
                else "ALLOW"
            ),
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
        allowed_providers=_intersect_allowlists(
            effective.allowed_providers,
            lower_precedence.allowed_providers,
        ),
        allowed_models=_intersect_allowlists(
            effective.allowed_models,
            lower_precedence.allowed_models,
        ),
        allowed_capabilities=_intersect_allowlists(
            effective.allowed_capabilities,
            lower_precedence.allowed_capabilities,
        ),
        required_model_capabilities=(
            effective.required_model_capabilities
            | lower_precedence.required_model_capabilities
        ),
        budgets=effective.budgets.tighten(lower_precedence.budgets),
        deadline=_earlier_deadline(effective.deadline, lower_precedence.deadline),
        approval_required=(
            effective.approval_required or lower_precedence.approval_required is True
        ),
        audit_level=_stricter_audit_level(
            effective.audit_level,
            lower_precedence.audit_level,
        ),
        capture_policy=_stricter_capture_policy(
            effective.capture_policy,
            lower_precedence.capture_policy,
        ),
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
) -> bool:
    forced_model = routing.force_model
    if forced_model is None:
        return False
    denied = False
    if (
        effective.allowed_models is not None
        and forced_model not in effective.allowed_models
    ):
        _add_reason(reasons, "model.force_not_allowed")
        denied = True
    missing_capabilities = effective.required_model_capabilities
    for capability in sorted(missing_capabilities):
        _add_reason(reasons, f"model.{capability}_required")
        denied = True
    return denied


def _add_reason(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _validate_empty_allowlists(
    effective: EffectiveConstraints,
    reasons: list[str],
) -> bool:
    denied = False
    for allowlist, reason in (
        (effective.allowed_providers, "provider.no_allowed_providers"),
        (effective.allowed_models, "model.no_allowed_models"),
        (effective.allowed_capabilities, "capability.no_allowed_capabilities"),
    ):
        if allowlist == frozenset():
            _add_reason(reasons, reason)
            denied = True
    return denied


def _earlier_deadline(
    existing: object,
    additional: object,
):
    if existing is None:
        return additional
    if additional is None:
        return existing
    return min(existing, additional)


def _stricter_audit_level(existing, additional):
    if additional is None:
        return existing
    order = {"minimal": 0, "standard": 1, "strict": 2}
    return additional if order[additional.value] > order[existing.value] else existing


def _stricter_capture_policy(existing, additional):
    if additional is None:
        return existing
    order = {"none": 0, "metadata_only": 1}
    return additional if order[additional.value] < order[existing.value] else existing
