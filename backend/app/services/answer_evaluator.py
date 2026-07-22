"""Strict, explicit Coach answer evaluation."""
from __future__ import annotations

import logging
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from ..agents.tools.context_budgets import ANSWER_EVAL
from ..config import settings
from ..observability import get_telemetry, trace_stage
from ..prompts import render_prompt
from ..schemas.coach import AnswerEvaluation, SpeechMetrics, VoiceToneResult
from .coach_contracts import CoachDiagnostic, configured_model_id, run_with_stage_deadline
from .jd_analyser import _split_jinja_output
from .llm_client import LLMClient
from .prompt_catalog import prompt_contract_block, prompt_metadata, source_contains
from .rubric_builder import build_rubric

logger = logging.getLogger(__name__)

_FOLLOW_UP_THRESHOLD = 6.0
_EVAL_DIMENSIONS = [
    "relevance",
    "star_structure",
    "technical_depth",
    "conciseness",
    "communication",
    "impact_metrics",
]


def _diagnostic(
    client: object,
    *,
    outcome: str,
    gates: list[str],
    duration_ms: int,
    execution_mode: str = "llm",
) -> CoachDiagnostic:
    if execution_mode != "llm":
        return CoachDiagnostic(
            stage="answer_evaluation",
            outcome=outcome,
            execution_mode=execution_mode,
            attempt_count=0,
            repair_count=0,
            gate_codes=gates,
            duration_ms=duration_ms,
        )
    metadata = prompt_metadata("answer_evaluation")
    return CoachDiagnostic(
        stage="answer_evaluation",
        outcome=outcome,
        execution_mode="llm",
        prompt_id=metadata.prompt_id,
        prompt_version=metadata.prompt_version,
        output_schema_version=metadata.schema_version,
        model_id=configured_model_id(client),
        attempt_count=1,
        repair_count=0,
        gate_codes=gates,
        duration_ms=duration_ms,
    )


def _no_score(
    client: object,
    *,
    state: str,
    outcome: str,
    gate: str,
    feedback: str,
    duration_ms: int,
    execution_mode: str = "llm",
) -> AnswerEvaluation:
    return AnswerEvaluation(
        evaluation_state=state,
        diagnostic=_diagnostic(
            client,
            outcome=outcome,
            gates=[gate],
            duration_ms=duration_ms,
            execution_mode=execution_mode,
        ),
        scores={},
        overall=None,
        feedback=feedback,
        strengths=[],
        improvements=["Please retry the evaluation."],
        evidence_references=[],
        follow_up_question=None,
        speech_coaching=[],
        rubric=None,
    )


class AnswerEvaluatorService:
    """Evaluate an answer without converting failures into neutral scores."""

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
        if not transcript.strip():
            return _no_score(
                self._client,
                state="invalid",
                outcome="invalid_output",
                gate="coach_answer_empty_transcript",
                feedback="No audible or written answer was provided. Please retry.",
                duration_ms=0,
                execution_mode="not_run",
            )

        system_prompt, user_prompt = _split_jinja_output(
            render_prompt(
                "answer_evaluation.j2",
                question=question,
                category=category,
                transcript=transcript,
                speech_metrics=(speech_metrics.model_dump() if speech_metrics else None),
                model_answer=model_answer,
                prompt_contract=prompt_contract_block("answer_evaluation"),
            )
        )
        started = time.monotonic()
        try:
            raw = await run_with_stage_deadline(
                self._client.complete_json(
                    system_prompt,
                    user_prompt,
                    max_tokens=ANSWER_EVAL.max_output,
                ),
                settings.HATCH_COACH_TIMEOUT_ANSWER_EVALUATION_SECONDS,
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            get_telemetry().record_model_call(
                workflow="coach_generation",
                provider=type(self._client).__name__,
                model_id=configured_model_id(self._client),
                duration_ms=duration_ms,
                outcome="failed",
            )
            get_telemetry().mark_current_error(
                "answer_evaluation_failed", "model_error"
            )
            gate = (
                "coach_stage_timeout"
                if isinstance(exc, TimeoutError)
                else "coach_evaluation_provider_unavailable"
            )
            logger.warning("Answer evaluation failed: %s", exc)
            return _no_score(
                self._client,
                state="unavailable",
                outcome="unavailable",
                gate=gate,
                feedback="Evaluation service is temporarily unavailable. Please retry.",
                duration_ms=duration_ms,
            )

        duration_ms = int((time.monotonic() - started) * 1000)
        get_telemetry().record_model_call(
            workflow="coach_generation",
            provider=type(self._client).__name__,
            model_id=configured_model_id(self._client),
            duration_ms=duration_ms,
        )
        evaluation = _parse_evaluation(
            raw,
            speech_metrics,
            transcript,
            client=self._client,
            duration_ms=duration_ms,
        )
        if evaluation.evaluation_state != "completed":
            return evaluation
        evaluation.rubric = build_rubric(
            evaluation,
            speech_metrics=speech_metrics,
            tone_result=tone_result,
            face_summary=(
                {
                    "eye_contact_pct": video_metrics.eye_contact_pct / 100.0,
                    "head_stability": video_metrics.head_stability,
                }
                if video_metrics
                else None
            ),
        )
        return evaluation


def _parse_evaluation(
    raw: Any,
    speech_metrics: SpeechMetrics | None,
    transcript: str = "",
    *,
    client: object | None = None,
    duration_ms: int = 0,
) -> AnswerEvaluation:
    client = client or object()
    if not isinstance(raw, dict) or not isinstance(raw.get("scores"), dict):
        return _no_score(
            client,
            state="invalid",
            outcome="invalid_output",
            gate="coach_evaluation_schema_invalid",
            feedback="Evaluation output was invalid. Please retry.",
            duration_ms=duration_ms,
        )

    raw_scores = raw["scores"]
    if set(raw_scores) != set(_EVAL_DIMENSIONS):
        return _no_score(
            client,
            state="invalid",
            outcome="invalid_output",
            gate="coach_evaluation_dimension_missing",
            feedback="Evaluation output was incomplete. Please retry.",
            duration_ms=duration_ms,
        )
    if any(
        isinstance(raw_scores[dimension], bool)
        or not isinstance(raw_scores[dimension], (int, float))
        or int(raw_scores[dimension]) != raw_scores[dimension]
        or not 0 <= int(raw_scores[dimension]) <= 10
        for dimension in _EVAL_DIMENSIONS
    ):
        return _no_score(
            client,
            state="invalid",
            outcome="invalid_output",
            gate="coach_evaluation_score_out_of_range",
            feedback="Evaluation scores were invalid. Please retry.",
            duration_ms=duration_ms,
        )
    scores = {dimension: int(raw_scores[dimension]) for dimension in _EVAL_DIMENSIONS}

    overall_raw = raw.get("overall")
    if (
        isinstance(overall_raw, bool)
        or not isinstance(overall_raw, (int, float))
        or not 0 <= float(overall_raw) <= 10
    ):
        return _no_score(
            client,
            state="invalid",
            outcome="invalid_output",
            gate="coach_evaluation_score_out_of_range",
            feedback="The overall evaluation score was invalid. Please retry.",
            duration_ms=duration_ms,
        )
    overall = float(overall_raw)
    mean = sum(scores.values()) / len(scores)
    if abs(overall - mean) > 1.0:
        return _no_score(
            client,
            state="invalid",
            outcome="invalid_output",
            gate="coach_evaluation_overall_inconsistent",
            feedback="The evaluation scores were inconsistent. Please retry.",
            duration_ms=duration_ms,
        )

    gates: list[str] = []
    metric_evidence = _metric_evidence_strings(speech_metrics)
    raw_references = raw.get("evidence_references", [])
    if not isinstance(raw_references, list):
        return _no_score(
            client,
            state="invalid",
            outcome="invalid_output",
            gate="coach_evaluation_schema_invalid",
            feedback="Evaluation evidence was invalid. Please retry.",
            duration_ms=duration_ms,
        )
    evidence_references = [
        reference
        for reference in raw_references
        if isinstance(reference, str)
        and (
            source_contains(reference, transcript)
            or any(source_contains(reference, metric) for metric in metric_evidence)
        )
    ][:6]
    if len(evidence_references) != len(raw_references):
        gates.append("coach_evaluation_evidence_ungrounded")

    follow_up = raw.get("follow_up_question")
    if overall < _FOLLOW_UP_THRESHOLD:
        if not isinstance(follow_up, str) or not follow_up.strip():
            weakest = min(_EVAL_DIMENSIONS, key=lambda dimension: (scores[dimension], dimension))
            follow_up = (
                "Could you give a more specific example that strengthens your "
                f"{weakest.replace('_', ' ')}?"
            )
            gates.append("coach_evaluation_followup_missing")
        else:
            follow_up = follow_up.strip()
    elif follow_up not in (None, ""):
        follow_up = None
        gates.append("coach_evaluation_followup_unexpected")
    else:
        follow_up = None

    speech_coaching: list[str] = []
    if speech_metrics:
        if speech_metrics.filler_count > 5:
            speech_coaching.append(
                f"Reduce filler words — detected {speech_metrics.filler_count} instances"
            )
        if speech_metrics.wpm > 180:
            speech_coaching.append(
                f"Slow down — speaking at {speech_metrics.wpm:.0f} WPM (target 130-160)"
            )
        elif 0 < speech_metrics.wpm < 100:
            speech_coaching.append(
                f"Speak a little faster — {speech_metrics.wpm:.0f} WPM feels slow"
            )
        if speech_metrics.hedging_count > 3:
            speech_coaching.append(
                "Reduce hedging phrases — "
                f"{speech_metrics.hedging_count} detected (e.g. 'I think', 'maybe')"
            )

    overall_one_decimal = float(
        Decimal(str(overall)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    )
    return AnswerEvaluation(
        evaluation_state="completed",
        diagnostic=_diagnostic(
            client,
            outcome="completed",
            gates=gates,
            duration_ms=duration_ms,
        ),
        scores=scores,
        overall=overall_one_decimal,
        feedback=str(raw.get("feedback") or ""),
        strengths=[str(item) for item in raw.get("strengths", []) if isinstance(item, str)],
        improvements=[
            str(item) for item in raw.get("improvements", []) if isinstance(item, str)
        ],
        evidence_references=evidence_references,
        follow_up_question=follow_up,
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
