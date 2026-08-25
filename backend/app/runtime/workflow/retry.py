"""Retry values for the workflow kernel."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta


_STABLE_CODE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_MAX_CODE_LENGTH = 128


def _normalized_code(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"retry {field} must be a stable code identifier")
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > _MAX_CODE_LENGTH
        or not _STABLE_CODE.fullmatch(normalized)
    ):
        raise ValueError(f"retry {field} must be a bounded stable code identifier")
    return normalized


def normalize_retry_metadata(
    reason: object, policy_id: object, policy_version: object
) -> tuple[str, str, int]:
    """Validate metadata at every retry persistence boundary."""
    normalized_reason = _normalized_code(reason, field="reason")
    normalized_policy_id = _normalized_code(policy_id, field="policy_id")
    if (
        isinstance(policy_version, bool)
        or not isinstance(policy_version, int)
        or policy_version < 1
    ):
        raise ValueError("retry policy_version must be positive")
    return normalized_reason, normalized_policy_id, policy_version


@dataclass(frozen=True)
class RetryFailure:
    """Metadata-only failure classification used to create a durable retry."""

    reason: str
    policy_id: str
    policy_version: int
    retry_after: timedelta = timedelta()

    def __post_init__(self) -> None:
        reason, policy_id, policy_version = normalize_retry_metadata(
            self.reason, self.policy_id, self.policy_version
        )
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "policy_id", policy_id)
        object.__setattr__(self, "policy_version", policy_version)
        if self.retry_after < timedelta():
            raise ValueError("retry_after cannot be negative")
