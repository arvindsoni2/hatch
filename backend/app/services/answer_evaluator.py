"""Answer Evaluator — STAR rubric scoring of interview answers via Claude."""
from __future__ import annotations

import logging
from typing import Any

from ..prompts import render_prompt
from ..schemas.coach import AnswerEvaluation, SpeechMetrics
from .claude_client import ClaudeClient
from .jd_analyser import _split_jinja_output

logger = logging.getLogger(__name__)

_FOLLOW_UP_THRESHOLD = 6.0  # Overall score below this triggers a follow-up question

_EVAL_DIMENSIONS = [
    "relevance", "star_structure", "technical_depth",
    "conciseness", "communication", "impact_metrics",
]


class AnswerEvaluatorService:
    """Evaluates interview answers using the STAR rubric via Claude."""

    def __init__(self, claude_client: ClaudeClient) -> None:
        self._client = claude_client

    async def evaluate(
        self,
        question: str,
        category: str,
        transcript: str,
        speech_metrics: SpeechMetrics | None = None,
        video_metrics: Any | None = None,
        model_answer: str | None = None,
    ) -> AnswerEvaluation:
        """Score an interview answer on 6 STAR dimensions.

        Args:
            question: The interview question text.
            category: Question category (Technical, Behavioural, etc.).
            transcript: The candidate's answer transcript.
            speech_metrics: Optional speech quality metrics.
            video_metrics: Optional video presentation metrics.
            model_answer: Optional reference model answer.

        Returns:
            AnswerEvaluation with dimension scores, feedback, and optional follow-up.
        """
        if not transcript.strip():
            return AnswerEvaluation(
                scores={dim: 0 for dim in _EVAL_DIMENSIONS},
                overall=0.0,
                feedback="No answer was provided.",
                strengths=[],
                improvements=["Provide a substantive answer to the question."],
            )

        system_prompt, user_prompt = _split_jinja_output(
            render_prompt(
                "answer_evaluation.j2",
                question=question,
                category=category,
                transcript=transcript,
                speech_metrics=speech_metrics.model_dump() if speech_metrics else None,
                model_answer=model_answer,
            )
        )

        try:
            raw = await self._client.complete_json(system_prompt, user_prompt, max_tokens=2048)
        except Exception as exc:
            logger.warning("Answer evaluation failed: %s — returning default scores", exc)
            return AnswerEvaluation(
                scores={dim: 5 for dim in _EVAL_DIMENSIONS},
                overall=5.0,
                feedback="Evaluation service temporarily unavailable.",
                strengths=[],
                improvements=["Please retry the evaluation."],
            )

        return _parse_evaluation(raw, speech_metrics)


def _parse_evaluation(raw: dict[str, Any], speech_metrics: SpeechMetrics | None) -> AnswerEvaluation:
    """Convert raw Claude response into AnswerEvaluation."""
    scores: dict[str, int] = {}
    for dim in _EVAL_DIMENSIONS:
        val = raw.get("scores", {}).get(dim, 5)
        scores[dim] = max(0, min(10, int(val)))

    overall = float(raw.get("overall", sum(scores.values()) / len(scores) if scores else 5.0))
    overall = max(0.0, min(10.0, overall))

    # Build speech coaching from metrics if available
    speech_coaching: list[str] = []
    if speech_metrics:
        if speech_metrics.filler_count > 5:
            speech_coaching.append(f"Reduce filler words — detected {speech_metrics.filler_count} instances")
        if speech_metrics.wpm > 180:
            speech_coaching.append(f"Slow down — speaking at {speech_metrics.wpm:.0f} WPM (target 130-160)")
        elif speech_metrics.wpm < 100 and speech_metrics.wpm > 0:
            speech_coaching.append(f"Speak a little faster — {speech_metrics.wpm:.0f} WPM feels slow")
        if speech_metrics.hedging_count > 3:
            speech_coaching.append(f"Reduce hedging phrases — {speech_metrics.hedging_count} detected (e.g. 'I think', 'maybe')")

    return AnswerEvaluation(
        scores=scores,
        overall=round(overall, 1),
        feedback=raw.get("feedback", ""),
        strengths=raw.get("strengths", []),
        improvements=raw.get("improvements", []),
        follow_up_question=raw.get("follow_up_question"),
        speech_coaching=speech_coaching,
    )
