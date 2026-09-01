"""Immutable, metadata-only contracts for deterministic policy decisions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .budgets import BudgetLimits

_STABLE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")


class AuditLevel(str, Enum):
    """Increasing levels require more decision/audit evidence."""

    MINIMAL = "minimal"
    STANDARD = "standard"
    STRICT = "strict"


class CapturePolicy(str, Enum):
    """Canonical capture levels; policy folding may only reduce capture."""

    METADATA_ONLY = "metadata_only"
    REDACTED = "redacted"
    DEBUG_CONTENT = "debug_content"
    DISABLED = "disabled"


def _validate_identifiers(values: frozenset[str], *, field_name: str) -> None:
    if any(not _STABLE_IDENTIFIER.fullmatch(value) for value in values):
        raise ValueError(f"{field_name} entries must be stable lowercase identifiers")


@dataclass(frozen=True)
class ConstraintSet:
    """A layer's restrictions; unset values express no additional restriction."""

    data_egress: bool | None = None
    allowed_providers: frozenset[str] | None = None
    allowed_models: frozenset[str] | None = None
    allowed_capabilities: frozenset[str] | None = None
    required_model_capabilities: frozenset[str] = frozenset()
    budgets: BudgetLimits = field(default_factory=BudgetLimits)
    deadline: datetime | None = None
    approval_required: bool | None = None
    audit_level: AuditLevel | None = None
    capture_policy: CapturePolicy | None = None

    def __post_init__(self) -> None:
        if self.data_egress is not None and not isinstance(self.data_egress, bool):
            raise ValueError("data_egress must be a boolean or None")
        if self.approval_required is not None and not isinstance(
            self.approval_required,
            bool,
        ):
            raise ValueError("approval_required must be a boolean or None")
        if self.deadline is not None and not isinstance(self.deadline, datetime):
            raise ValueError("deadline must be a datetime or None")
        if self.deadline is not None and self.deadline.tzinfo is None:
            raise ValueError("deadline must be timezone-aware")
        allowed_providers = (
            None
            if self.allowed_providers is None
            else frozenset(self.allowed_providers)
        )
        allowed_models = (
            None if self.allowed_models is None else frozenset(self.allowed_models)
        )
        allowed_capabilities = (
            None
            if self.allowed_capabilities is None
            else frozenset(self.allowed_capabilities)
        )
        required_model_capabilities = frozenset(self.required_model_capabilities)
        if allowed_providers is not None:
            _validate_identifiers(allowed_providers, field_name="allowed_providers")
        if allowed_models is not None:
            _validate_identifiers(allowed_models, field_name="allowed_models")
        if allowed_capabilities is not None:
            _validate_identifiers(
                allowed_capabilities,
                field_name="allowed_capabilities",
            )
        _validate_identifiers(
            required_model_capabilities,
            field_name="required_model_capabilities",
        )
        object.__setattr__(self, "allowed_providers", allowed_providers)
        object.__setattr__(self, "allowed_models", allowed_models)
        object.__setattr__(self, "allowed_capabilities", allowed_capabilities)
        object.__setattr__(
            self,
            "required_model_capabilities",
            required_model_capabilities,
        )
        if self.audit_level is not None:
            object.__setattr__(self, "audit_level", AuditLevel(self.audit_level))
        if self.capture_policy is not None:
            object.__setattr__(
                self,
                "capture_policy",
                CapturePolicy(self.capture_policy),
            )


@dataclass(frozen=True)
class PolicyLayer:
    """Named policy input wrapper used for security, workflow, and user layers."""

    constraints: ConstraintSet = field(default_factory=ConstraintSet)


@dataclass(frozen=True)
class RoutingPreferences:
    """Lowest-precedence selection preferences with no authorization authority."""

    force_model: str | None = None
    model_capabilities: frozenset[str] = frozenset()
    constraints: ConstraintSet = field(default_factory=ConstraintSet)

    def __post_init__(self) -> None:
        if self.force_model is not None and not _STABLE_IDENTIFIER.fullmatch(
            self.force_model
        ):
            raise ValueError("force_model must be a stable lowercase identifier")
        model_capabilities = frozenset(self.model_capabilities)
        _validate_identifiers(model_capabilities, field_name="model_capabilities")
        object.__setattr__(self, "model_capabilities", model_capabilities)


@dataclass(frozen=True)
class EffectiveConstraints:
    """Final intersection of all policy layers, without untrusted free text."""

    data_egress: bool = True
    allowed_providers: frozenset[str] | None = None
    allowed_models: frozenset[str] | None = None
    allowed_capabilities: frozenset[str] | None = None
    required_model_capabilities: frozenset[str] = frozenset()
    budgets: BudgetLimits = field(default_factory=BudgetLimits)
    deadline: datetime | None = None
    approval_required: bool = False
    audit_level: AuditLevel = AuditLevel.MINIMAL
    capture_policy: CapturePolicy = CapturePolicy.METADATA_ONLY
    forced_model: str | None = None


@dataclass(frozen=True)
class PolicyDecision:
    """Deterministic authorization outcome and its bounded reason codes."""

    decision: str
    reason_codes: tuple[str, ...]
    effective_constraints: EffectiveConstraints

    def __post_init__(self) -> None:
        if self.decision not in {"ALLOW", "DENY", "REQUIRE_APPROVAL"}:
            raise ValueError("decision must be ALLOW, DENY, or REQUIRE_APPROVAL")
        _validate_identifiers(frozenset(self.reason_codes), field_name="reason_codes")
