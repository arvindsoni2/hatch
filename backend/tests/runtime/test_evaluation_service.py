"""Bounded deterministic-first runtime evaluation contracts."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.runtime.contracts import EvaluationPolicy
from app.runtime.evaluation.service import (
    EvaluationFinding,
    EvaluationService,
    EvaluationUsage,
)
from app.runtime.control import BudgetLimits, EffectiveConstraints


class RecordingEvaluator:
    def __init__(self, finding: EvaluationFinding) -> None:
        self.finding = finding
        self.calls: list[object] = []

    async def __call__(self, subject: object) -> EvaluationFinding:
        self.calls.append(subject)
        return self.finding


@pytest.mark.asyncio
async def test_deterministic_failure_stops_unneeded_model_evaluation() -> None:
    model_evaluator = RecordingEvaluator(EvaluationFinding.passed("model_passed"))
    service = EvaluationService(
        deterministic_validators=(
            lambda _subject: EvaluationFinding.failed("schema_invalid", terminal=True),
        ),
        model_evaluator=model_evaluator,
    )

    result = await service.evaluate(
        {"not": "a valid output"}, policy=EvaluationPolicy(max_evaluations=3)
    )

    assert result.status == "failed"
    assert result.reason_codes == ("schema_invalid",)
    assert model_evaluator.calls == []
    assert result.evaluator_types == ("deterministic",)


@pytest.mark.asyncio
async def test_evaluation_order_is_bounded_and_never_recurses() -> None:
    calls: list[str] = []

    def deterministic(_subject: object) -> EvaluationFinding:
        calls.append("deterministic")
        return EvaluationFinding.passed("schema_valid")

    def heuristic(_subject: object) -> EvaluationFinding:
        calls.append("heuristic")
        return EvaluationFinding.review_required("heuristic_ambiguous")

    model = RecordingEvaluator(EvaluationFinding.review_required("model_ambiguous"))
    human = RecordingEvaluator(EvaluationFinding.passed("human_approved"))
    service = EvaluationService(
        deterministic_validators=(deterministic,),
        heuristics=(heuristic,),
        model_evaluator=model,
        human_reviewer=human,
    )

    result = await service.evaluate(
        {"result_ref": "synthetic"}, policy=EvaluationPolicy(max_evaluations=3)
    )

    assert calls == ["deterministic", "heuristic"]
    assert len(model.calls) == 1
    assert human.calls == []
    assert result.status == "review_required"
    assert result.evaluator_types == ("deterministic", "heuristic", "model")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"input_tokens": 10},
        {"output_tokens": 10},
        {"cost_usd": Decimal("1")},
    ],
)
async def test_evaluation_stops_at_each_shared_budget_boundary(
    kwargs: dict[str, object],
) -> None:
    evaluator = RecordingEvaluator(EvaluationFinding.passed("ok"))
    result = await EvaluationService(deterministic_validators=(evaluator,)).evaluate(
        object(),
        policy=EvaluationPolicy(max_evaluations=2),
        constraints=EffectiveConstraints(
            budgets=BudgetLimits(
                max_input_tokens=10, max_output_tokens=10, max_cost_usd=Decimal("1")
            )
        ),
        usage=EvaluationUsage(**kwargs),
    )
    assert result.status == "review_required"
    assert evaluator.calls == []


@pytest.mark.asyncio
async def test_evaluation_deadline_is_absolute_and_repairs_are_bounded() -> None:
    result = await EvaluationService().evaluate(
        object(),
        policy=EvaluationPolicy(max_evaluations=2, max_repairs=1),
        constraints=EffectiveConstraints(
            deadline=datetime.now(timezone.utc) - timedelta(seconds=1)
        ),
    )
    assert "evaluation_deadline_exhausted" in result.reason_codes


@pytest.mark.asyncio
async def test_evaluation_tightens_policy_and_shared_count_limit() -> None:
    first = RecordingEvaluator(EvaluationFinding.passed("first_passed"))
    second = RecordingEvaluator(EvaluationFinding.passed("second_passed"))
    result = await EvaluationService(deterministic_validators=(first, second)).evaluate(
        object(),
        policy=EvaluationPolicy(max_evaluations=4),
        constraints=EffectiveConstraints(budgets=BudgetLimits(max_evaluations=2)),
        usage=EvaluationUsage(evaluations=1),
    )

    assert first.calls
    assert second.calls == []
    assert result.reason_codes[-1] == "evaluation_budget_exhausted"


@pytest.mark.asyncio
async def test_repair_does_not_start_when_shared_repair_limit_is_exhausted() -> None:
    repair = RecordingEvaluator(EvaluationFinding.passed("repair_passed"))
    result = await EvaluationService(
        heuristics=(lambda _subject: EvaluationFinding.review_required("ambiguous"),),
        repair_evaluators=(repair,),
    ).evaluate(
        object(),
        policy=EvaluationPolicy(max_evaluations=3, max_repairs=2),
        constraints=EffectiveConstraints(budgets=BudgetLimits(max_repairs=1)),
        usage=EvaluationUsage(repairs=1),
    )

    assert repair.calls == []
    assert result.reason_codes[-1] == "repair_budget_exhausted"


@pytest.mark.asyncio
async def test_work_below_every_budget_boundary_can_complete() -> None:
    validator = RecordingEvaluator(EvaluationFinding.passed("valid"))
    result = await EvaluationService(deterministic_validators=(validator,)).evaluate(
        object(),
        policy=EvaluationPolicy(max_evaluations=2),
        constraints=EffectiveConstraints(
            deadline=datetime.now(timezone.utc) + timedelta(seconds=1),
            budgets=BudgetLimits(
                max_evaluations=2,
                max_input_tokens=11,
                max_output_tokens=11,
                max_cost_usd=Decimal("1.01"),
            ),
        ),
        usage=EvaluationUsage(
            input_tokens=10,
            output_tokens=10,
            cost_usd=Decimal("1"),
        ),
    )

    assert result.status == "passed"
    assert validator.calls


@pytest.mark.asyncio
async def test_async_evaluator_cannot_cross_absolute_deadline() -> None:
    async def slow(_subject: object) -> EvaluationFinding:
        await asyncio.sleep(0.05)
        return EvaluationFinding.passed("too_late")

    result = await EvaluationService(deterministic_validators=(slow,)).evaluate(
        object(),
        policy=EvaluationPolicy(max_evaluations=1),
        constraints=EffectiveConstraints(
            deadline=datetime.now(timezone.utc) + timedelta(milliseconds=5)
        ),
    )

    assert result.status == "review_required"
    assert result.reason_codes == ("evaluation_deadline_exhausted",)
