"""Rubric Synthesiser — LLM-as-judge enrichment of the SessionRubric.

Takes the deterministic rubric from rubric_builder.py as a baseline and asks
the LLM to produce narrative evidence (quoting the actual transcript) and a
sharper focus statement. Falls back to the deterministic rubric if the LLM
call fails, so slow/unavailable local Ollama never breaks evaluation.
"""
from __future__ import annotations

import json
import logging
import re
import time

from langchain_core.messages import HumanMessage, SystemMessage

from ..agents.tools.llm_factory import get_json_model
from ..config import settings
from ..observability import get_telemetry, trace_stage
from ..schemas.coach import (
    AnswerEvaluation,
    RubricDimension,
    SessionRubric,
    SpeechMetrics,
    VoiceToneResult,
)
from .coach_contracts import CoachDiagnostic, configured_model_id, run_with_stage_deadline
from .rubric_builder import build_rubric
from .prompt_catalog import prompt_contract_block, prompt_metadata, source_contains

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert interview coach. Given a candidate's answer transcript, their content scores, and delivery signals, produce an enriched rubric.

Label claims as OBSERVATION, INTERPRETATION, or RECOMMENDATION. For each
dimension, write 1-2 OBSERVATION evidence items by QUOTING SHORT PHRASES from
the transcript or citing exact deterministic metrics. Interpretations must be
framed as interpretations. Drills are RECOMMENDATIONS, not candidate facts.
Keep each evidence string under 100 characters.

Also write a 'focus_for_next_session' sentence identifying the 1-2 weakest dimensions.

Scores, score bands, and dimension membership are immutable inputs. Repeat them
exactly; only evidence, drill wording, and focus_for_next_session may be enriched.

Respond with valid JSON only:
{
  "dimensions": {
    "<dim_name>": {
      "score": <0-10 int>,
      "score_band": "<strong|good|needs_work|weak>",
      "evidence": ["<quote or metric>", "<quote or metric>"],
      "drill": "<specific practice action>"
    }
  },
  "focus_for_next_session": "<sentence>"
}
"""


def _build_user_prompt(
    transcript: str,
    evaluation: AnswerEvaluation,
    speech_metrics: SpeechMetrics | None,
    tone_result: VoiceToneResult | None,
    baseline_rubric: SessionRubric,
) -> str:
    parts: list[str] = [
        f"TRANSCRIPT:\n{transcript[:3000]}",
        f"\nCONTENT SCORES (0-10): {json.dumps(evaluation.scores)}",
        f"OVERALL: {evaluation.overall}",
        f"STRENGTHS: {evaluation.strengths}",
        f"IMPROVEMENTS: {evaluation.improvements}",
    ]
    if speech_metrics:
        parts.append(
            f"\nDELIVERY SIGNALS: "
            f"WPM={speech_metrics.wpm:.0f}, fillers={speech_metrics.filler_count}, "
            f"long_pauses={speech_metrics.pause_count}, star_coverage={speech_metrics.star_coverage:.2f}"
        )
    if tone_result:
        parts.append(
            f"\nVOCAL TONE: arousal={tone_result.arousal:.2f}, "
            f"valence={tone_result.valence:.2f}, dominance={tone_result.dominance:.2f}"
        )

    dim_keys = list(baseline_rubric.dimensions.keys())
    parts.append(f"\nPRODUCE EVIDENCE FOR THESE DIMENSIONS: {dim_keys}")

    return "\n".join(parts)


def _parse_llm_rubric(
    raw: dict,
    baseline: SessionRubric,
    transcript: str,
    metric_context: str,
) -> tuple[SessionRubric, list[str]]:
    """Merge narrative only while retaining authoritative deterministic scores."""
    merged: dict[str, RubricDimension] = dict(baseline.dimensions)
    gates: list[str] = []

    llm_dims = raw.get("dimensions", {})
    if not isinstance(llm_dims, dict):
        return baseline, ["coach_rubric_dimension_missing"]
    if set(baseline.dimensions) - set(llm_dims):
        return baseline, ["coach_rubric_dimension_missing"]
    for dim_name, dim_data in llm_dims.items():
        if dim_name not in baseline.dimensions:
            gates.append("coach_rubric_optional_dimension_unexpected")
            continue
        if not isinstance(dim_data, dict):
            gates.append("coach_rubric_dimension_missing")
            continue
        try:
            authoritative = baseline.dimensions[dim_name]
            if (
                dim_data.get("score") != authoritative.score
                or dim_data.get("score_band") != authoritative.score_band
            ):
                gates.append("coach_rubric_score_mutation")
            raw_evidence = dim_data.get("evidence") or []
            evidence = [
                str(item)
                for item in raw_evidence[:2]
                if _evidence_is_grounded(str(item), transcript, metric_context)
            ]
            if len(evidence) != len(raw_evidence[:2]):
                gates.append("coach_rubric_evidence_ungrounded")
            drill = dim_data.get("drill") or ""
            merged[dim_name] = RubricDimension(
                score=authoritative.score,
                score_band=authoritative.score_band,
                evidence=evidence or authoritative.evidence,
                drill=str(drill) if drill else authoritative.drill,
            )
        except Exception as exc:
            logger.debug("Skipping malformed LLM rubric dim '%s': %s", dim_name, exc)
            gates.append("coach_rubric_dimension_missing")

    gates = list(dict.fromkeys(gates))
    if "coach_rubric_dimension_missing" in gates:
        return baseline, gates
    focus = raw.get("focus_for_next_session") or baseline.focus_for_next_session
    return (
        SessionRubric(dimensions=merged, focus_for_next_session=str(focus)),
        gates,
    )


def _evidence_is_grounded(
    evidence: str,
    transcript: str,
    metric_context: str,
) -> bool:
    """Accept a transcript quote or an exact deterministic metric citation."""
    if source_contains(evidence, transcript) or source_contains(evidence, metric_context):
        return True
    quoted_only = re.fullmatch(r"\s*['\"]([^'\"]+)['\"]\s*[.!]?\s*", evidence)
    if quoted_only and source_contains(quoted_only.group(1), transcript):
        return True
    return False


class RubricSynthesiserService:
    """Enriches a deterministic SessionRubric with LLM-generated narrative evidence.

    Uses the primary/json model from llm_factory (lazy-initialised on first call).
    Falls back to the deterministic rubric if the LLM is unavailable or returns
    malformed JSON.
    """

    def __init__(self) -> None:
        self._llm = None  # lazy — avoids profile load at startup time

    def _get_llm(self):
        if self._llm is None:
            self._llm = get_json_model()
        return self._llm

    @staticmethod
    def _diagnostic(
        model: object,
        *,
        outcome: str,
        gates: list[str],
        duration_ms: int,
    ) -> CoachDiagnostic:
        metadata = prompt_metadata("rubric_synthesis")
        return CoachDiagnostic(
            stage="rubric_synthesis",
            outcome=outcome,
            execution_mode="llm",
            prompt_id=metadata.prompt_id,
            prompt_version=metadata.prompt_version,
            output_schema_version=metadata.schema_version,
            model_id=configured_model_id(model),
            attempt_count=1,
            repair_count=0,
            gate_codes=gates,
            duration_ms=duration_ms,
        )

    @trace_stage("coach_generation", "validate_output")
    async def synthesise(
        self,
        transcript: str,
        evaluation: AnswerEvaluation,
        speech_metrics: SpeechMetrics | None = None,
        tone_result: VoiceToneResult | None = None,
    ) -> SessionRubric:
        """Return an LLM-enriched SessionRubric with transcript-quoted evidence.

        Args:
            transcript: The candidate's answer text (up to 3 000 chars used).
            evaluation: The LLM-scored AnswerEvaluation (provides content scores).
            speech_metrics: Optional delivery metrics — adds 'delivery' dimension.
            tone_result: Optional vocal tone — adds 'vocal_confidence' dimension.

        Returns:
            SessionRubric with narrative evidence per dimension. Falls back to
            the deterministic rubric if the LLM call fails.
        """
        baseline = build_rubric(evaluation, speech_metrics=speech_metrics, tone_result=tone_result)

        user_prompt = _build_user_prompt(
            transcript, evaluation, speech_metrics, tone_result, baseline
        )
        messages = [
            SystemMessage(
                content=(
                    _SYSTEM_PROMPT
                    + "\n\n"
                    + prompt_contract_block("rubric_synthesis")
                )
            ),
            HumanMessage(content=user_prompt),
        ]

        model = None
        started = time.monotonic()
        try:
            model = self._get_llm()
            response = await run_with_stage_deadline(
                model.ainvoke(messages),
                settings.HATCH_COACH_TIMEOUT_RUBRIC_ENRICHMENT_SECONDS,
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            get_telemetry().record_model_call(
                workflow="coach_generation",
                provider=type(model).__name__ if model is not None else "configured",
                model_id=str(getattr(model, "model", "configured")),
                duration_ms=duration_ms,
                outcome="failed",
            )
            get_telemetry().mark_current_error(
                "rubric_synthesis_failed",
                "model_error",
            )
            logger.warning(
                "RubricSynthesiser LLM call failed (%s) — using deterministic rubric.", exc
            )
            gate = (
                "coach_stage_timeout"
                if isinstance(exc, TimeoutError)
                else "coach_rubric_provider_unavailable"
            )
            baseline.diagnostic = self._diagnostic(
                model or self,
                outcome="fallback_deterministic",
                gates=[gate],
                duration_ms=duration_ms,
            )
            return baseline
        duration_ms = int((time.monotonic() - started) * 1000)
        get_telemetry().record_model_call(
            workflow="coach_generation",
            provider=type(model).__name__,
            model_id=str(getattr(model, "model", "configured")),
            duration_ms=duration_ms,
        )
        try:
            raw = json.loads(response.content)
            metric_context = _metric_context(speech_metrics, tone_result)
            rubric, gates = _parse_llm_rubric(
                raw, baseline, transcript, metric_context
            )
            rubric.diagnostic = self._diagnostic(
                model,
                outcome=(
                    "fallback_deterministic"
                    if "coach_rubric_dimension_missing" in gates
                    else "completed"
                ),
                gates=gates,
                duration_ms=duration_ms,
            )
            return rubric
        except Exception as exc:
            get_telemetry().record_validation_failure(
                "coach_generation",
                "rubric_response_invalid",
            )
            get_telemetry().mark_current_error(
                "rubric_response_invalid",
                "validation_failure",
            )
            logger.warning(
                "RubricSynthesiser response was invalid (%s) — using deterministic rubric.",
                exc,
            )
            baseline.diagnostic = self._diagnostic(
                model,
                outcome="fallback_deterministic",
                gates=["coach_rubric_dimension_missing"],
                duration_ms=duration_ms,
            )
            return baseline


def _metric_context(
    speech_metrics: SpeechMetrics | None,
    tone_result: VoiceToneResult | None,
) -> str:
    values: list[str] = []
    if speech_metrics:
        values.extend(
            [
                f"{speech_metrics.wpm:g} WPM",
                f"{speech_metrics.filler_count} filler words",
                f"{speech_metrics.pause_count} pauses",
                f"{speech_metrics.star_coverage:g} STAR coverage",
            ]
        )
    if tone_result:
        values.extend(
            [
                f"{tone_result.arousal:g} arousal",
                f"{tone_result.valence:g} valence",
                f"{tone_result.dominance:g} dominance",
            ]
        )
    return "\n".join(values)
