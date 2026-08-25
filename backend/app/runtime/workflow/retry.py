"""Retry values for the workflow kernel."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class RetryFailure:
    """Metadata-only failure classification used to create a durable retry."""

    reason: str
    policy_id: str
    policy_version: int
    retry_after: timedelta = timedelta()

    def __post_init__(self) -> None:
        if not self.reason or not self.policy_id:
            raise ValueError("retry reason and policy_id are required")
        if self.policy_version < 1:
            raise ValueError("retry policy_version must be positive")
        if self.retry_after < timedelta():
            raise ValueError("retry_after cannot be negative")
