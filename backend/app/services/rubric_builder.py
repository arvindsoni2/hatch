"""Rubric builder — deterministic construction of per-dimension rubric entries.

The rubric has two kinds of dimensions:
- Content dimensions (relevance, star_structure, …): scores come from the LLM evaluator;
  evidence uses only transcript/metric references already accepted by its grounding gate.
- Perception dimensions (delivery, vocal_confidence): fully deterministic from
  SpeechMetrics / VoiceToneResult — no LLM required.
- presence: Phase D only; never added here (omit, don't zero).
"""
from __future__ import annotations

from ..schemas.coach import (
    AnswerEvaluation,
    RubricDimension,
    ScoreBand,
    SessionRubric,
    SpeechMetrics,
    VoiceToneResult,
)

# Ordered list of content dimensions (match answer_evaluator._EVAL_DIMENSIONS)
CONTENT_DIMENSIONS = [
    "relevance",
    "star_structure",
    "technical_depth",
    "conciseness",
    "communication",
    "impact_metrics",
]

_DRILL_MAP: dict[str, str] = {
    "relevance": "Practise the PREP method: Point, Reason, Example, Point — keep every sentence tied to the question.",
    "star_structure": "Record a 2-min STAR story answer daily; self-review for all four sections.",
    "technical_depth": "Prepare a 'deep dive' card for each key project: tech chosen, trade-offs, alternatives rejected.",
    "conciseness": "Time-box answers to 2 min. Cut any sentence that doesn't add new information.",
    "communication": "Read your answer aloud after writing; replace jargon with plain language.",
    "impact_metrics": "For every outcome, add a number: %, £/$, time saved, scale. Practise 'so what?' follow-throughs.",
    "delivery": "Record yourself answering mock questions; count fillers with a tally. Aim to halve the count weekly.",
    "vocal_confidence": "Power-pose warm-up before interviews; practise speaking slower and louder on recorded drills.",
    "presence": "Practice maintaining eye contact with camera; record 2 minutes speaking without looking away.",
}


def drill_for_dimension(dimension: str) -> str:
    """Return the stable deterministic practice drill for a rubric dimension."""
    return _DRILL_MAP.get(
        dimension,
        f"Practise {dimension.replace('_', ' ')} in mock answers.",
    )


def score_to_band(score: int) -> ScoreBand:
    """Map a 0–10 score to a human label."""
    if score >= 8:
        return "strong"
    if score >= 6:
        return "good"
    if score >= 4:
        return "needs_work"
    return "weak"


# ── Delivery dimension (from SpeechMetrics) ───────────────────────────────────

def build_delivery_dimension(metrics: SpeechMetrics) -> RubricDimension:
    """Build the 'delivery' rubric dimension from deterministic SpeechMetrics."""
    evidence: list[str] = []
    penalty = 0  # accumulated deduction from ideal score of 10

    # Pace
    if metrics.wpm > 0:
        if 130 <= metrics.wpm <= 160:
            evidence.append(f"Good pace — {metrics.wpm:.0f} WPM (target 130–160 WPM).")
        elif metrics.wpm > 180:
            evidence.append(f"Speaking fast at {metrics.wpm:.0f} WPM; slowing down aids clarity.")
            penalty += 2
        elif metrics.wpm > 160:
            evidence.append(f"Slightly fast at {metrics.wpm:.0f} WPM; aim for 130–160 WPM.")
            penalty += 1
        else:
            evidence.append(f"Speaking slowly at {metrics.wpm:.0f} WPM; more energy would help.")
            penalty += 1

    # Fillers
    if metrics.filler_count > 15:
        evidence.append(f"{metrics.filler_count} filler words detected — significantly reduces impact.")
        penalty += 6
    elif metrics.filler_count > 10:
        evidence.append(f"{metrics.filler_count} filler words detected — significantly reduces impact.")
        penalty += 4
    elif metrics.filler_count > 5:
        evidence.append(f"{metrics.filler_count} filler words detected; reducing these strengthens delivery.")
        penalty += 2
    elif metrics.filler_count > 0:
        evidence.append(f"{metrics.filler_count} filler word(s) detected — minor.")
        penalty += 1

    # Long pauses
    if metrics.pause_count > 3:
        evidence.append(f"{metrics.pause_count} long pauses detected; practise bridging phrases.")
        penalty += 2
    elif metrics.pause_count > 1:
        evidence.append(f"{metrics.pause_count} long pause(s) detected.")
        penalty += 1

    if not evidence:
        evidence.append("No delivery issues detected.")

    score = max(0, min(10, 10 - penalty))
    return RubricDimension(
        score=score,
        score_band=score_to_band(score),
        evidence=evidence[:2],  # cap at 2 per spec
        drill=_DRILL_MAP["delivery"],
    )


# ── Vocal confidence dimension (from VoiceToneResult) ────────────────────────

def build_tone_dimension(tone: VoiceToneResult) -> RubricDimension:
    """Build the 'vocal_confidence' rubric dimension from VoiceToneResult."""
    evidence: list[str] = []

    energy_label = "high" if tone.arousal > 0.6 else ("moderate" if tone.arousal > 0.35 else "low")
    evidence.append(f"Energy (arousal): {energy_label} ({tone.arousal:.2f}).")

    if tone.dominance > 0.6:
        evidence.append(f"Confident, assertive delivery (dominance {tone.dominance:.2f}).")
    elif tone.dominance < 0.3:
        evidence.append(f"Subdued delivery — low assertiveness (dominance {tone.dominance:.2f}); aim for more confidence.")

    # Score: weight dominance most heavily (it proxies confidence)
    raw = (tone.dominance * 5 + tone.arousal * 3 + tone.valence * 2) * 10 / 10
    score = max(0, min(10, round(raw)))

    if not evidence:
        evidence.append(f"Tone data available: arousal {tone.arousal:.2f}, valence {tone.valence:.2f}, dominance {tone.dominance:.2f}.")

    return RubricDimension(
        score=score,
        score_band=score_to_band(score),
        evidence=evidence[:2],
        drill=_DRILL_MAP["vocal_confidence"],
    )


# ── Content dimensions (from LLM AnswerEvaluation) ────────────────────────────

def build_content_dimensions(evaluation: AnswerEvaluation) -> dict[str, RubricDimension]:
    """Map LLM evaluation scores to RubricDimension entries for all content dimensions."""
    dims: dict[str, RubricDimension] = {}

    grounded_evidence = evaluation.evidence_references or []

    for dim_name in CONTENT_DIMENSIONS:
        score = evaluation.scores.get(dim_name, 5)
        band = score_to_band(score)

        evidence = grounded_evidence[:1] or [f"Score: {score}/10 — {band}."]

        dims[dim_name] = RubricDimension(
            score=score,
            score_band=band,
            evidence=evidence[:2],
            drill=_DRILL_MAP.get(dim_name, f"Practise {dim_name.replace('_', ' ')} in mock answers."),
        )

    return dims


# ── Top-level builder ─────────────────────────────────────────────────────────

# ── Presence dimension (Phase D — from face summary data) ─────────────────────

def build_presence_dimension(face_summary: dict) -> RubricDimension:
    """Build the 'presence' rubric dimension from FaceSummary data (Phase D).

    Args:
        face_summary: Dict with keys eye_contact_pct (0.0-1.0), head_stability (lower=better).

    Returns:
        RubricDimension for the 'presence' dimension.
    """
    eye_contact = face_summary.get("eye_contact_pct", 0.0)
    stability = face_summary.get("head_stability", 1.0)

    evidence: list[str] = [
        f"Eye contact: {eye_contact:.0%}",
        f"Head stability: {'good' if stability < 0.3 else 'needs work'} (stddev {stability:.2f})",
    ]

    presence_score = min(10, int((eye_contact * 7) + ((1 - min(stability, 1.0)) * 3)))
    return RubricDimension(
        score=presence_score,
        score_band=score_to_band(presence_score),
        evidence=evidence[:2],
        drill=_DRILL_MAP["presence"],
    )


def build_rubric(
    evaluation: AnswerEvaluation,
    speech_metrics: SpeechMetrics | None = None,
    tone_result: VoiceToneResult | None = None,
    face_summary: dict | None = None,
) -> SessionRubric:
    """Build a complete SessionRubric from available signals.

    Dimensions appear only when the underlying signal exists.

    Args:
        evaluation: The LLM-produced AnswerEvaluation.
        speech_metrics: Optional — adds 'delivery' dimension when present.
        tone_result: Optional — adds 'vocal_confidence' dimension when present.
        face_summary: Optional (Phase D) — adds 'presence' dimension when present.

    Returns:
        SessionRubric with populated dimensions and focus_for_next_session.
    """
    dimensions: dict[str, RubricDimension] = {}

    # Content dims — always present
    dimensions.update(build_content_dimensions(evaluation))

    # Delivery — only when speech data available
    if speech_metrics is not None:
        dimensions["delivery"] = build_delivery_dimension(speech_metrics)

    # Vocal confidence — only when tone data available
    if tone_result is not None:
        dimensions["vocal_confidence"] = build_tone_dimension(tone_result)

    # Presence — Phase D opt-in, only when face data is present
    if face_summary is not None:
        dimensions["presence"] = build_presence_dimension(face_summary)

    # Focus: find the 1-2 weakest dimensions
    sorted_dims = sorted(dimensions.items(), key=lambda kv: kv[1].score)
    weakest = [name for name, _ in sorted_dims[:2]]
    if weakest:
        focus = "Focus next session on: " + " and ".join(
            name.replace("_", " ") for name in weakest
        ) + "."
    else:
        focus = "Continue practising all dimensions."

    return SessionRubric(dimensions=dimensions, focus_for_next_session=focus)
