"""Canonical enum values shared across runtime boundaries."""

from enum import Enum


class ExecutionStrategy(str, Enum):
    SINGLE_PASS = "single_pass"
    VALIDATE_AND_REPAIR = "validate_and_repair"
    FALLBACK_ON_FAILURE = "fallback_on_failure"


class RiskClass(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ExecutionResultCode(str, Enum):
    SUCCESS = "success"
    VALIDATION_FAILURE = "validation_failure"
    POLICY_DENIED = "policy_denied"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    TRANSIENT_FAILURE = "transient_failure"
    PERMANENT_FAILURE = "permanent_failure"
    OUTCOME_UNKNOWN = "outcome_unknown"
