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

from langchain_core.messages import HumanMessage, SystemMessage

from ..agents.tools.llm_factory import get_json_model
from ..schemas.coach import (
    AnswerEvaluation,
    RubricDimension,
    SessionRubric,
    SpeechMetrics,
    VoiceToneResult,
)
from .rubric_builder import build_rubric, score_to_band
from .prompt_catalog import prompt_contract_block, source_contains

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert interview coach. Given a candidate's answer transcript, their content scores, and delivery signals, produce an enriched rubric.

Label claims as OBSERVATION, INTERPRETATION, or RECOMMENDATION. For each
dimension, write 1-2 OBSERVATION evidence items by QUOTING SHORT PHRASES from
the transcript or citing exact deterministic metrics. Interpretations must be
framed as interpretations. Drills are RECOMMENDATIONS, not candidate facts.
Keep each evidence string under 100 characters.

Also write a 'focus_for_next_session' sentence identifying the 1-2 weakest dimensions.

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
) -> SessionRubric:
    """Merge LLM output into the baseline rubric; fall back per-dim on parse error."""
    merged: dict[str, RubricDimension] = dict(baseline.dimensions)

    llm_dims = raw.get("dimensions", {})
    for dim_name, dim_data in llm_dims.items():
        if not isinstance(dim_data, dict):
            continue
        try:
            score = max(0, min(10, int(dim_data.get("score", baseline.dimensions.get(dim_name, RubricDimension()).score))))
            band = dim_data.get("score_band") or score_to_band(score)
            evidence = [
                str(item)
                for item in (dim_data.get("evidence") or [])[:2]
                if _evidence_is_grounded(str(item), transcript, metric_context)
            ]
            drill = dim_data.get("drill") or ""
            if isinstance(evidence, list) and evidence:
                merged[dim_name] = RubricDimension(
                    score=score,
                    score_band=band,
                    evidence=evidence,
                    drill=str(drill) if drill else (merged.get(dim_name, RubricDimension()).drill),
                )
        except Exception as exc:
            logger.debug("Skipping malformed LLM rubric dim '%s': %s", dim_name, exc)

    focus = raw.get("focus_for_next_session") or baseline.focus_for_next_session
    return SessionRubric(dimensions=merged, focus_for_next_session=str(focus))


def _evidence_is_grounded(
    evidence: str,
    transcript: str,
    metric_context: str,
) -> bool:
    """Accept a transcript quote or an exact deterministic metric citation."""
    if source_contains(evidence, transcript) or source_contains(evidence, metric_context):
        return True
    quoted = re.findall(r"['\"]([^'\"]+)['\"]", evidence)
    if any(source_contains(quote, transcript) for quote in quoted):
        return True
    return any(
        source_contains(token, metric_context)
        for token in re.findall(r"\b\d+(?:\.\d+)?%?\b", evidence)
    )


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

        try:
            response = await self._get_llm().ainvoke(messages)
            raw = json.loads(response.content)
            return _parse_llm_rubric(raw, baseline, transcript, user_prompt)
        except Exception as exc:
            logger.warning(
                "RubricSynthesiser LLM call failed (%s) — using deterministic rubric.", exc
            )
            return baseline
