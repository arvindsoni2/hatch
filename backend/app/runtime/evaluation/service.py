"""Deterministic-first, non-recursive evaluation orchestration."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from ..contracts import EvaluationPolicy
from ..control import EffectiveConstraints
from ..observability import RuntimeCorrelation, RuntimeTelemetry
from .validators import EvaluationFinding, Evaluator


@dataclass(frozen=True)
class EvaluationResult:
    """Content-free final outcome and evaluator provenance."""

    status: str
    reason_codes: tuple[str, ...]
    evaluator_types: tuple[str, ...]


@dataclass(frozen=True)
class EvaluationUsage:
    """Immutable usage snapshot shared by all bounded runtime work."""

    evaluations: int = 0
    repairs: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if any(
            isinstance(v, bool) or not isinstance(v, int) or v < 0
            for v in (
                self.evaluations,
                self.repairs,
                self.input_tokens,
                self.output_tokens,
            )
        ):
            raise ValueError("usage counts must be non-negative integers")
        if (
            not isinstance(self.cost_usd, Decimal)
            or not self.cost_usd.is_finite()
            or self.cost_usd < 0
        ):
            raise ValueError("cost_usd must be a non-negative finite Decimal")


class EvaluationService:
    """Run the finite evaluator ladder without retaining the subject content."""

    def __init__(
        self,
        *,
        deterministic_validators: tuple[Evaluator, ...] = (),
        heuristics: tuple[Evaluator, ...] = (),
        model_evaluator: Evaluator | None = None,
        human_reviewer: Evaluator | None = None,
        repair_evaluators: tuple[Evaluator, ...] = (),
        clock: Callable[[], datetime] | None = None,
        telemetry: RuntimeTelemetry | None = None,
    ) -> None:
        self._deterministic_validators = deterministic_validators
        self._heuristics = heuristics
        self._model_evaluator = model_evaluator
        self._human_reviewer = human_reviewer
        self._repair_evaluators = repair_evaluators
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._telemetry = telemetry or RuntimeTelemetry()

    async def evaluate(
        self,
        subject: object,
        *,
        policy: EvaluationPolicy,
        constraints: EffectiveConstraints | None = None,
        usage: EvaluationUsage | None = None,
        correlation: RuntimeCorrelation | None = None,
    ) -> EvaluationResult:
        """Evaluate once through each permitted stage, never recursively."""
        findings: list[EvaluationFinding] = []
        evaluator_types: list[str] = []
        effective = constraints or EffectiveConstraints()
        snapshot = usage or EvaluationUsage()
        limits = effective.budgets
        max_evaluations = (
            min(policy.max_evaluations, limits.max_evaluations)
            if limits.max_evaluations is not None
            else policy.max_evaluations
        )
        max_repairs = (
            min(policy.max_repairs, limits.max_repairs)
            if limits.max_repairs is not None
            else policy.max_repairs
        )
        if effective.deadline is not None and self._clock() >= effective.deadline:
            return _budget_exhausted(
                findings, evaluator_types, "evaluation_deadline_exhausted"
            )
        if (
            limits.max_input_tokens is not None
            and snapshot.input_tokens >= limits.max_input_tokens
        ):
            return _budget_exhausted(
                findings, evaluator_types, "input_token_budget_exhausted"
            )
        if (
            limits.max_output_tokens is not None
            and snapshot.output_tokens >= limits.max_output_tokens
        ):
            return _budget_exhausted(
                findings, evaluator_types, "output_token_budget_exhausted"
            )
        if limits.max_cost_usd is not None and snapshot.cost_usd >= limits.max_cost_usd:
            return _budget_exhausted(findings, evaluator_types, "cost_budget_exhausted")

        async def run(
            evaluator: Evaluator, evaluator_type: str
        ) -> tuple[EvaluationFinding | None, str | None]:
            if snapshot.evaluations + len(findings) >= max_evaluations:
                return None, "evaluation_budget_exhausted"
            if effective.deadline is not None and self._clock() >= effective.deadline:
                return None, "evaluation_deadline_exhausted"
            if (
                evaluator_type == "repair"
                and snapshot.repairs + sum(t == "repair" for t in evaluator_types)
                >= max_repairs
            ):
                return None, "repair_budget_exhausted"
            with self._telemetry.span(
                f"evaluation.{evaluator_type}", correlation or RuntimeCorrelation()
            ):
                finding = evaluator(subject)
                if inspect.isawaitable(finding):
                    remaining = (
                        None
                        if effective.deadline is None
                        else (effective.deadline - self._clock()).total_seconds()
                    )
                    if remaining is not None and remaining <= 0:
                        finding.close() if inspect.iscoroutine(finding) else None
                        return None, "evaluation_deadline_exhausted"
                    try:
                        finding = (
                            await asyncio.wait_for(finding, timeout=remaining)
                            if remaining is not None
                            else await finding
                        )
                    except TimeoutError:
                        return None, "evaluation_deadline_exhausted"
            if not isinstance(finding, EvaluationFinding):
                raise TypeError("evaluator must return EvaluationFinding")
            findings.append(finding)
            evaluator_types.append(evaluator_type)
            return finding, None

        for validator in self._deterministic_validators:
            finding, exhausted = await run(validator, "deterministic")
            if finding is None:
                return _budget_exhausted(findings, evaluator_types, exhausted)
            if finding.terminal:
                return _result("failed", findings, evaluator_types)

        for heuristic in self._heuristics:
            finding, exhausted = await run(heuristic, "heuristic")
            if finding is None:
                return _budget_exhausted(findings, evaluator_types, exhausted)
            if finding.terminal:
                return _result("failed", findings, evaluator_types)

        model_needed = any(item.status == "review_required" for item in findings)
        if model_needed and self._model_evaluator is not None:
            finding, exhausted = await run(self._model_evaluator, "model")
            if finding is None:
                return _budget_exhausted(findings, evaluator_types, exhausted)
            if finding.terminal:
                return _result("failed", findings, evaluator_types)

        repair_needed = bool(findings and findings[-1].status == "review_required")
        if repair_needed:
            for repair in self._repair_evaluators:
                finding, exhausted = await run(repair, "repair")
                if finding is None:
                    return _budget_exhausted(findings, evaluator_types, exhausted)
                if finding.terminal:
                    return _result("failed", findings, evaluator_types)
                if finding.status != "review_required":
                    break

        human_needed = bool(findings and findings[-1].status == "review_required")
        if human_needed and self._human_reviewer is not None:
            finding, exhausted = await run(self._human_reviewer, "human")
            if finding is None:
                return _budget_exhausted(findings, evaluator_types, exhausted)
            if finding.terminal:
                return _result("failed", findings, evaluator_types)

        if any(item.status == "failed" for item in findings):
            return _result("failed", findings, evaluator_types)
        if findings and findings[-1].status == "review_required":
            return _result("review_required", findings, evaluator_types)
        return _result("passed", findings, evaluator_types)


def _budget_exhausted(
    findings: list[EvaluationFinding],
    evaluator_types: list[str],
    code: str | None = "evaluation_budget_exhausted",
) -> EvaluationResult:
    return EvaluationResult(
        status="review_required",
        reason_codes=tuple(
            dict.fromkeys(
                [item for finding in findings for item in finding.reason_codes]
                + [code or "evaluation_budget_exhausted"]
            )
        ),
        evaluator_types=tuple(evaluator_types),
    )


def _result(
    status: str,
    findings: list[EvaluationFinding],
    evaluator_types: list[str],
) -> EvaluationResult:
    return EvaluationResult(
        status=status,
        reason_codes=tuple(
            dict.fromkeys(code for finding in findings for code in finding.reason_codes)
        ),
        evaluator_types=tuple(evaluator_types),
    )
