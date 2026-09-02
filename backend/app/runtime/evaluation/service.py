"""Deterministic-first, non-recursive evaluation orchestration."""

from __future__ import annotations

import inspect
from dataclasses import dataclass

from ..contracts import EvaluationPolicy
from .validators import EvaluationFinding, Evaluator


@dataclass(frozen=True)
class EvaluationResult:
    """Content-free final outcome and evaluator provenance."""

    status: str
    reason_codes: tuple[str, ...]
    evaluator_types: tuple[str, ...]


class EvaluationService:
    """Run the finite evaluator ladder without retaining the subject content."""

    def __init__(
        self,
        *,
        deterministic_validators: tuple[Evaluator, ...] = (),
        heuristics: tuple[Evaluator, ...] = (),
        model_evaluator: Evaluator | None = None,
        human_reviewer: Evaluator | None = None,
    ) -> None:
        self._deterministic_validators = deterministic_validators
        self._heuristics = heuristics
        self._model_evaluator = model_evaluator
        self._human_reviewer = human_reviewer

    async def evaluate(
        self, subject: object, *, policy: EvaluationPolicy
    ) -> EvaluationResult:
        """Evaluate once through each permitted stage, never recursively."""
        findings: list[EvaluationFinding] = []
        evaluator_types: list[str] = []

        async def run(
            evaluator: Evaluator, evaluator_type: str
        ) -> EvaluationFinding | None:
            if len(findings) >= policy.max_evaluations:
                return None
            finding = evaluator(subject)
            if inspect.isawaitable(finding):
                finding = await finding
            if not isinstance(finding, EvaluationFinding):
                raise TypeError("evaluator must return EvaluationFinding")
            findings.append(finding)
            evaluator_types.append(evaluator_type)
            return finding

        for validator in self._deterministic_validators:
            finding = await run(validator, "deterministic")
            if finding is None:
                return _budget_exhausted(findings, evaluator_types)
            if finding.terminal:
                return _result("failed", findings, evaluator_types)

        for heuristic in self._heuristics:
            finding = await run(heuristic, "heuristic")
            if finding is None:
                return _budget_exhausted(findings, evaluator_types)
            if finding.terminal:
                return _result("failed", findings, evaluator_types)

        model_needed = any(item.status == "review_required" for item in findings)
        if model_needed and self._model_evaluator is not None:
            finding = await run(self._model_evaluator, "model")
            if finding is None:
                return _budget_exhausted(findings, evaluator_types)
            if finding.terminal:
                return _result("failed", findings, evaluator_types)

        human_needed = bool(findings and findings[-1].status == "review_required")
        if human_needed and self._human_reviewer is not None:
            finding = await run(self._human_reviewer, "human")
            if finding is None:
                return _budget_exhausted(findings, evaluator_types)
            if finding.terminal:
                return _result("failed", findings, evaluator_types)

        if any(item.status == "failed" for item in findings):
            return _result("failed", findings, evaluator_types)
        if findings and findings[-1].status == "review_required":
            return _result("review_required", findings, evaluator_types)
        return _result("passed", findings, evaluator_types)


def _budget_exhausted(
    findings: list[EvaluationFinding], evaluator_types: list[str]
) -> EvaluationResult:
    return EvaluationResult(
        status="review_required",
        reason_codes=tuple(
            dict.fromkeys(
                [code for finding in findings for code in finding.reason_codes]
                + ["evaluation_budget_exhausted"]
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
