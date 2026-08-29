"""Explicit bounded budget narrowing for Control Plane constraints."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class BudgetLimits:
    """Optional ceilings where ``None`` is unbounded and lower values tighten."""

    max_attempts: int | None = None
    max_evaluations: int | None = None
    max_cost_usd: Decimal | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    max_retries: int | None = None
    max_repairs: int | None = None

    def __post_init__(self) -> None:
        self._validate_limit("max_attempts", self.max_attempts, minimum=1)
        self._validate_limit("max_evaluations", self.max_evaluations, minimum=0)
        self._validate_cost(self.max_cost_usd)
        self._validate_limit("max_input_tokens", self.max_input_tokens, minimum=0)
        self._validate_limit("max_output_tokens", self.max_output_tokens, minimum=0)
        self._validate_limit("max_retries", self.max_retries, minimum=0)
        self._validate_limit("max_repairs", self.max_repairs, minimum=0)

    @staticmethod
    def _validate_limit(name: str, value: int | None, *, minimum: int) -> None:
        if value is None:
            return
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f"{name} must be an integer greater than or equal to {minimum}")

    @staticmethod
    def _validate_cost(value: Decimal | None) -> None:
        if value is None:
            return
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            raise ValueError("max_cost_usd must be a non-negative finite Decimal")

    def tighten(self, other: BudgetLimits) -> BudgetLimits:
        """Return the non-widening intersection of two budget ceilings."""
        return BudgetLimits(
            max_attempts=_minimum_defined(self.max_attempts, other.max_attempts),
            max_evaluations=_minimum_defined(
                self.max_evaluations,
                other.max_evaluations,
            ),
            max_cost_usd=_minimum_defined(self.max_cost_usd, other.max_cost_usd),
            max_input_tokens=_minimum_defined(
                self.max_input_tokens,
                other.max_input_tokens,
            ),
            max_output_tokens=_minimum_defined(
                self.max_output_tokens,
                other.max_output_tokens,
            ),
            max_retries=_minimum_defined(self.max_retries, other.max_retries),
            max_repairs=_minimum_defined(self.max_repairs, other.max_repairs),
        )


def _minimum_defined[T: (int, Decimal)](left: T | None, right: T | None) -> T | None:
    if left is None:
        return right
    if right is None:
        return left
    return min(left, right)
