"""Explicit bounded budget narrowing for Control Plane constraints."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BudgetLimits:
    """Optional ceilings where ``None`` is unbounded and lower values tighten."""

    max_attempts: int | None = None
    max_evaluations: int | None = None

    def __post_init__(self) -> None:
        self._validate_limit("max_attempts", self.max_attempts, minimum=1)
        self._validate_limit("max_evaluations", self.max_evaluations, minimum=0)

    @staticmethod
    def _validate_limit(name: str, value: int | None, *, minimum: int) -> None:
        if value is None:
            return
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f"{name} must be an integer greater than or equal to {minimum}")

    def tighten(self, other: BudgetLimits) -> BudgetLimits:
        """Return the non-widening intersection of two budget ceilings."""
        return BudgetLimits(
            max_attempts=_minimum_defined(self.max_attempts, other.max_attempts),
            max_evaluations=_minimum_defined(
                self.max_evaluations,
                other.max_evaluations,
            ),
        )


def _minimum_defined(left: int | None, right: int | None) -> int | None:
    if left is None:
        return right
    if right is None:
        return left
    return min(left, right)
