"""Tests for AnswerEvaluatorService — good answer scores high, poor answer low, follow-up triggered."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.coach import AnswerEvaluation, SpeechMetrics
from app.services.answer_evaluator import AnswerEvaluatorService, _FOLLOW_UP_THRESHOLD

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# ---------------------------------------------------------------------------
# Shared mock responses
# ---------------------------------------------------------------------------

GOOD_EVAL_RESPONSE = {
    "scores": {
        "relevance": 9,
        "star_structure": 8,
        "technical_depth": 9,
        "conciseness": 8,
        "communication": 8,
        "impact_metrics": 9,
    },
    "overall": 8.5,
    "feedback": "Excellent STAR structure with specific quantitative outcomes.",
    "strengths": ["Clear STAR structure", "Quantified outcomes", "Technical depth"],
    "improvements": ["Could mention team size"],
    "follow_up_question": None,
    "speech_coaching": [],
}

POOR_EVAL_RESPONSE = {
    "scores": {
        "relevance": 4,
        "star_structure": 2,
        "technical_depth": 3,
        "conciseness": 4,
        "communication": 4,
        "impact_metrics": 2,
    },
    "overall": 3.2,
    "feedback": "The answer lacks specifics and relies heavily on vague language.",
    "strengths": ["Some effort at structure"],
    "improvements": ["Add a specific example", "Quantify outcomes", "Reduce filler words"],
    "follow_up_question": "Can you give me a specific example with numbers?",
    "speech_coaching": ["Try to reduce filler words like 'um' and 'basically'."],
}


@pytest.fixture()
def mock_claude_good():
    claude = MagicMock()
    claude.complete_json = AsyncMock(return_value=GOOD_EVAL_RESPONSE)
    return claude


@pytest.fixture()
def mock_claude_poor():
    claude = MagicMock()
    claude.complete_json = AsyncMock(return_value=POOR_EVAL_RESPONSE)
    return claude


@pytest.fixture()
def good_answer():
    data = json.loads((FIXTURES_DIR / "sample_answers_good.json").read_text())
    return data


@pytest.fixture()
def poor_answer():
    data = json.loads((FIXTURES_DIR / "sample_answers_poor.json").read_text())
    return data


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_good_answer_scores_high(mock_claude_good, good_answer) -> None:
    """A strong STAR answer should score above 7.0 overall."""
    evaluator = AnswerEvaluatorService(mock_claude_good)
    result = await evaluator.evaluate(
        question=good_answer["question"],
        category=good_answer["category"],
        transcript=good_answer["transcript"],
    )
    assert isinstance(result, AnswerEvaluation)
    assert result.overall >= 7.0


@pytest.mark.asyncio
async def test_poor_answer_scores_low(mock_claude_poor, poor_answer) -> None:
    """A vague answer with fillers should score below 5.0 overall."""
    evaluator = AnswerEvaluatorService(mock_claude_poor)
    result = await evaluator.evaluate(
        question=poor_answer["question"],
        category=poor_answer["category"],
        transcript=poor_answer["transcript"],
    )
    assert result.overall < 5.0


@pytest.mark.asyncio
async def test_follow_up_triggered_for_poor_answer(mock_claude_poor, poor_answer) -> None:
    """A follow_up_question is returned when overall score < _FOLLOW_UP_THRESHOLD."""
    evaluator = AnswerEvaluatorService(mock_claude_poor)
    result = await evaluator.evaluate(
        question=poor_answer["question"],
        category=poor_answer["category"],
        transcript=poor_answer["transcript"],
    )
    assert result.overall < _FOLLOW_UP_THRESHOLD
    assert result.follow_up_question is not None


@pytest.mark.asyncio
async def test_no_follow_up_for_good_answer(mock_claude_good, good_answer) -> None:
    """No follow_up_question when the answer scores well."""
    evaluator = AnswerEvaluatorService(mock_claude_good)
    result = await evaluator.evaluate(
        question=good_answer["question"],
        category=good_answer["category"],
        transcript=good_answer["transcript"],
    )
    assert result.follow_up_question is None


@pytest.mark.asyncio
async def test_evaluate_with_speech_metrics(mock_claude_good, good_answer) -> None:
    """evaluate() accepts optional speech_metrics without error."""
    evaluator = AnswerEvaluatorService(mock_claude_good)
    metrics = SpeechMetrics(filler_count=2, wpm=145.0, hedging_count=1, duration_ms=45000, pause_count=3)
    result = await evaluator.evaluate(
        question=good_answer["question"],
        category=good_answer["category"],
        transcript=good_answer["transcript"],
        speech_metrics=metrics,
    )
    assert isinstance(result, AnswerEvaluation)


@pytest.mark.asyncio
async def test_evaluate_returns_all_six_dimensions(mock_claude_good, good_answer) -> None:
    """AnswerEvaluation.scores contains all 6 required dimension keys."""
    evaluator = AnswerEvaluatorService(mock_claude_good)
    result = await evaluator.evaluate(
        question=good_answer["question"],
        category=good_answer["category"],
        transcript=good_answer["transcript"],
    )
    expected_keys = {"relevance", "star_structure", "technical_depth", "conciseness", "communication", "impact_metrics"}
    assert expected_keys.issubset(set(result.scores.keys()))


@pytest.mark.asyncio
async def test_follow_up_threshold_constant() -> None:
    """_FOLLOW_UP_THRESHOLD is 6.0 as specified."""
    assert _FOLLOW_UP_THRESHOLD == 6.0


@pytest.mark.asyncio
async def test_evaluation_keeps_only_transcript_or_metric_evidence(good_answer) -> None:
    raw = {
        **GOOD_EVAL_RESPONSE,
        "evidence_references": [
            good_answer["transcript"][:30],
            "145 WPM",
            "Candidate led a team of 500",
        ],
    }
    client = MagicMock()
    client.complete_json = AsyncMock(return_value=raw)
    evaluator = AnswerEvaluatorService(client)

    result = await evaluator.evaluate(
        question=good_answer["question"],
        category=good_answer["category"],
        transcript=good_answer["transcript"],
        speech_metrics=SpeechMetrics(wpm=145),
    )

    assert good_answer["transcript"][:30] in result.evidence_references
    assert "145 WPM" in result.evidence_references
    assert "Candidate led a team of 500" not in result.evidence_references
    assert result.strengths == [good_answer["transcript"][:30], "145 WPM"]
    assert all("500" not in item for item in result.improvements)
    combined = "".join(client.complete_json.await_args.args[:2])
    assert '"prompt_id": "answer_evaluation"' in combined
    assert "OBSERVATION" in combined
    assert result.diagnostic is not None
    assert result.diagnostic.gate_codes == ["coach_evaluation_evidence_ungrounded"]


@pytest.mark.asyncio
async def test_evaluation_records_provider_parse_attempts(good_answer) -> None:
    client = MagicMock(model="configured-model")
    client.last_json_attempt_count = 3
    client.complete_json = AsyncMock(return_value=GOOD_EVAL_RESPONSE)

    result = await AnswerEvaluatorService(client).evaluate(
        question=good_answer["question"],
        category=good_answer["category"],
        transcript=good_answer["transcript"],
    )

    assert result.diagnostic is not None
    assert result.diagnostic.attempt_count == 3


@pytest.mark.asyncio
async def test_provider_failure_is_unavailable_without_neutral_score(good_answer) -> None:
    client = MagicMock()
    client.complete_json = AsyncMock(side_effect=RuntimeError("offline"))

    result = await AnswerEvaluatorService(client).evaluate(
        question=good_answer["question"],
        category=good_answer["category"],
        transcript=good_answer["transcript"],
    )

    assert result.evaluation_state == "unavailable"
    assert result.scores == {}
    assert result.overall is None
    assert result.rubric is None
    assert result.diagnostic is not None
    assert result.diagnostic.gate_codes == ["coach_evaluation_provider_unavailable"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation", "gate"),
    [
        ({"scores": {"relevance": 8}}, "coach_evaluation_dimension_missing"),
        ({"scores": {**GOOD_EVAL_RESPONSE["scores"], "relevance": 11}}, "coach_evaluation_score_out_of_range"),
        ({"overall": 2.0}, "coach_evaluation_overall_inconsistent"),
    ],
)
async def test_invalid_evaluation_contract_has_no_score(
    good_answer, mutation, gate
) -> None:
    raw = {**GOOD_EVAL_RESPONSE, **mutation}
    client = MagicMock()
    client.complete_json = AsyncMock(return_value=raw)

    result = await AnswerEvaluatorService(client).evaluate(
        question=good_answer["question"],
        category=good_answer["category"],
        transcript=good_answer["transcript"],
    )

    assert result.evaluation_state == "invalid"
    assert result.scores == {}
    assert result.overall is None
    assert result.rubric is None
    assert result.diagnostic is not None
    assert gate in result.diagnostic.gate_codes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overall", "supplied_followup", "expects_followup", "gate"),
    [
        (5.9, None, True, "coach_evaluation_followup_missing"),
        (6.0, "An unexpected follow-up", False, "coach_evaluation_followup_unexpected"),
    ],
)
async def test_followup_threshold_is_enforced_deterministically(
    good_answer, overall, supplied_followup, expects_followup, gate
) -> None:
    scores = {dimension: 6 for dimension in GOOD_EVAL_RESPONSE["scores"]}
    raw = {
        **GOOD_EVAL_RESPONSE,
        "scores": scores,
        "overall": overall,
        "follow_up_question": supplied_followup,
    }
    client = MagicMock()
    client.complete_json = AsyncMock(return_value=raw)

    result = await AnswerEvaluatorService(client).evaluate(
        question=good_answer["question"],
        category=good_answer["category"],
        transcript=good_answer["transcript"],
    )

    assert (result.follow_up_question is not None) is expects_followup
    assert result.diagnostic is not None
    assert gate in result.diagnostic.gate_codes


@pytest.mark.asyncio
async def test_empty_transcript_is_invalid_without_model_call() -> None:
    client = MagicMock()
    client.complete_json = AsyncMock()

    result = await AnswerEvaluatorService(client).evaluate(
        question="Question?",
        category="Technical",
        transcript="   ",
    )

    assert result.evaluation_state == "invalid"
    assert result.scores == {}
    assert result.overall is None
    assert result.diagnostic is not None
    assert result.diagnostic.gate_codes == ["coach_answer_empty_transcript"]
    client.complete_json.assert_not_awaited()
