"""Bounded deterministic-first runtime evaluation contracts."""

from __future__ import annotations

import pytest

from app.runtime.contracts import EvaluationPolicy
from app.runtime.evaluation.service import EvaluationFinding, EvaluationService


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
