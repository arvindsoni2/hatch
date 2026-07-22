"""Answer Evaluator — STAR rubric scoring of interview answers via Claude."""
from __future__ import annotations

import logging
import time
from typing import Any

from ..prompts import render_prompt
from ..observability import get_telemetry, trace_stage
from ..schemas.coach import AnswerEvaluation, SpeechMetrics, VoiceToneResult
from .llm_client import LLMClient
from ..agents.tools.context_budgets import ANSWER_EVAL
from .jd_analyser import _split_jinja_output
from .rubric_builder import build_rubric
from .prompt_catalog import prompt_contract_block, source_contains

logger = logging.getLogger(__name__)

_FOLLOW_UP_THRESHOLD = 6.0  # Overall score below this triggers a follow-up question

_EVAL_DIMENSIONS = [
    "relevance", "star_structure", "technical_depth",
    "conciseness", "communication", "impact_metrics",
]


class AnswerEvaluatorService:
    """Evaluates interview answers using the STAR rubric via Claude."""

    def __init__(self, claude_client: LLMClient) -> None:
        self._client = claude_client

    @trace_stage("coach_generation", "validate_output")
    async def evaluate(
        self,
        question: str,
        category: str,
        transcript: str,
        speech_metrics: SpeechMetrics | None = None,
        video_metrics: Any | None = None,
        model_answer: str | None = None,
        tone_result: VoiceToneResult | None = None,
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
                prompt_contract=prompt_contract_block("answer_evaluation"),
            )
        )

        started = time.monotonic()
        try:
            raw = await self._client.complete_json(
                system_prompt,
                user_prompt,
                max_tokens=ANSWER_EVAL.max_output,
            )
            get_telemetry().record_model_call(
                workflow="coach_generation",
                provider=type(self._client).__name__,
                model_id=str(getattr(self._client, "model", "configured")),
                duration_ms=(time.monotonic() - started) * 1000,
            )
        except Exception as exc:
            get_telemetry().record_model_call(
                workflow="coach_generation",
                provider=type(self._client).__name__,
                model_id=str(getattr(self._client, "model", "configured")),
                duration_ms=(time.monotonic() - started) * 1000,
                outcome="failed",
            )
            get_telemetry().mark_current_error(
                "answer_evaluation_failed",
                "model_error",
            )
            logger.warning("Answer evaluation failed: %s — returning default scores", exc)
            return AnswerEvaluation(
                scores={dim: 5 for dim in _EVAL_DIMENSIONS},
                overall=5.0,
                feedback="Evaluation service temporarily unavailable.",
                strengths=[],
                improvements=["Please retry the evaluation."],
            )

        evaluation = _parse_evaluation(raw, speech_metrics, transcript)
        evaluation.rubric = build_rubric(
            evaluation,
            speech_metrics=speech_metrics,
            tone_result=tone_result,
            face_summary=(
                {
                    "eye_contact_pct": video_metrics.eye_contact_pct / 100.0,
                    "head_stability": video_metrics.head_stability,
                }
                if video_metrics else None
            ),
        )
        return evaluation


def _parse_evaluation(
    raw: dict[str, Any],
    speech_metrics: SpeechMetrics | None,
    transcript: str = "",
) -> AnswerEvaluation:
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

    metric_evidence = _metric_evidence_strings(speech_metrics)
    evidence_references = [
        str(evidence)
        for evidence in raw.get("evidence_references", [])
        if isinstance(evidence, str)
        and (
            source_contains(evidence, transcript)
            or any(source_contains(evidence, metric) for metric in metric_evidence)
        )
    ][:6]

    return AnswerEvaluation(
        scores=scores,
        overall=round(overall, 1),
        feedback=raw.get("feedback", ""),
        strengths=raw.get("strengths", []),
        improvements=raw.get("improvements", []),
        evidence_references=evidence_references,
        follow_up_question=raw.get("follow_up_question"),
        speech_coaching=speech_coaching,
    )


def _metric_evidence_strings(metrics: SpeechMetrics | None) -> list[str]:
    if metrics is None:
        return []
    return [
        f"{metrics.wpm:g} WPM",
        f"{metrics.filler_count} filler words",
        f"{metrics.hedging_count} hedging phrases",
        f"{metrics.pause_count} pauses",
        f"{metrics.duration_ms} milliseconds",
        f"{metrics.star_coverage:g} STAR coverage",
    ]
