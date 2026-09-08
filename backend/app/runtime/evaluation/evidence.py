"""Explicit, content-free evaluation lineage values."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationLineage:
    """Durable IDs linking primary, repair, fallback, and evaluator work."""

    primary_execution_id: str | None = None
    repair_execution_id: str | None = None
    fallback_execution_id: str | None = None
    evaluation_execution_id: str | None = None
