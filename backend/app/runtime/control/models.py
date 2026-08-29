"""Immutable, metadata-only contracts for deterministic policy decisions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .budgets import BudgetLimits

_STABLE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")


def _validate_identifiers(values: frozenset[str], *, field_name: str) -> None:
    if any(not _STABLE_IDENTIFIER.fullmatch(value) for value in values):
        raise ValueError(f"{field_name} entries must be stable lowercase identifiers")


@dataclass(frozen=True)
class ConstraintSet:
    """A layer's restrictions; unset values express no additional restriction."""

    data_egress: bool | None = None
    allowed_models: frozenset[str] | None = None
    required_model_capabilities: frozenset[str] = frozenset()
    budgets: BudgetLimits = field(default_factory=BudgetLimits)

    def __post_init__(self) -> None:
        if self.data_egress is not None and not isinstance(self.data_egress, bool):
            raise ValueError("data_egress must be a boolean or None")
        allowed_models = (
            None if self.allowed_models is None else frozenset(self.allowed_models)
        )
        required_model_capabilities = frozenset(self.required_model_capabilities)
        if allowed_models is not None:
            _validate_identifiers(allowed_models, field_name="allowed_models")
        _validate_identifiers(
            required_model_capabilities,
            field_name="required_model_capabilities",
        )
        object.__setattr__(self, "allowed_models", allowed_models)
        object.__setattr__(
            self,
            "required_model_capabilities",
            required_model_capabilities,
        )


@dataclass(frozen=True)
class PolicyLayer:
    """Named policy input wrapper used for security, workflow, and user layers."""

    constraints: ConstraintSet = field(default_factory=ConstraintSet)


@dataclass(frozen=True)
class RoutingPreferences:
    """Lowest-precedence selection preferences and bounded model capability metadata."""

    force_model: str | None = None
    model_capabilities: frozenset[str] = frozenset()
    constraints: ConstraintSet = field(default_factory=ConstraintSet)

    def __post_init__(self) -> None:
        if self.force_model is not None and not _STABLE_IDENTIFIER.fullmatch(self.force_model):
            raise ValueError("force_model must be a stable lowercase identifier")
        model_capabilities = frozenset(self.model_capabilities)
        _validate_identifiers(model_capabilities, field_name="model_capabilities")
        object.__setattr__(self, "model_capabilities", model_capabilities)


@dataclass(frozen=True)
class EffectiveConstraints:
    """Final intersection of all policy layers, without untrusted free text."""

    data_egress: bool = True
    allowed_models: frozenset[str] | None = None
    required_model_capabilities: frozenset[str] = frozenset()
    budgets: BudgetLimits = field(default_factory=BudgetLimits)
    forced_model: str | None = None


@dataclass(frozen=True)
class PolicyDecision:
    """Deterministic authorization outcome and its bounded reason codes."""

    decision: str
    reason_codes: tuple[str, ...]
    effective_constraints: EffectiveConstraints

    def __post_init__(self) -> None:
        if self.decision not in {"ALLOW", "DENY"}:
            raise ValueError("decision must be ALLOW or DENY")
        _validate_identifiers(frozenset(self.reason_codes), field_name="reason_codes")
