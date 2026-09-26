"""Small, content-free evaluation findings and evaluator contracts."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

_REASON_CODE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
EvaluationStatus: TypeAlias = Literal["passed", "failed", "review_required"]
Evaluator: TypeAlias = Callable[
    [object], "EvaluationFinding | Awaitable[EvaluationFinding]"
]


@dataclass(frozen=True)
class EvaluationFinding:
    """One bounded, metadata-only evaluator outcome."""

    status: EvaluationStatus
    reason_codes: tuple[str, ...]
    terminal: bool = False

    def __post_init__(self) -> None:
        if self.status not in {"passed", "failed", "review_required"}:
            raise ValueError("invalid evaluation status")
        if self.terminal and self.status != "failed":
            raise ValueError("only failed evaluation findings can be terminal")
        if not self.reason_codes or any(
            not _REASON_CODE.fullmatch(code) for code in self.reason_codes
        ):
            raise ValueError("evaluation reason codes must be stable identifiers")

    @classmethod
    def passed(cls, reason_code: str) -> "EvaluationFinding":
        return cls("passed", (reason_code,))

    @classmethod
    def failed(cls, reason_code: str, *, terminal: bool = False) -> "EvaluationFinding":
        return cls("failed", (reason_code,), terminal=terminal)

    @classmethod
    def review_required(cls, reason_code: str) -> "EvaluationFinding":
        return cls("review_required", (reason_code,))


def validate_metadata(value: Any) -> dict[str, str | int | float | bool]:
    """Permit only small evaluator metadata, never the evaluated content."""
    if not isinstance(value, dict):
        raise ValueError("evaluation metadata must be a mapping")
    safe: dict[str, str | int | float | bool] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not _REASON_CODE.fullmatch(key):
            raise ValueError("evaluation metadata keys must be stable identifiers")
        if isinstance(item, bool):
            safe[key] = item
        elif isinstance(item, int) and not isinstance(item, bool):
            safe[key] = item
        elif isinstance(item, float) and item == item and abs(item) != float("inf"):
            safe[key] = item
        elif isinstance(item, str) and _REASON_CODE.fullmatch(item):
            safe[key] = item
        else:
            raise ValueError("evaluation metadata must be bounded and content-free")
    return safe
