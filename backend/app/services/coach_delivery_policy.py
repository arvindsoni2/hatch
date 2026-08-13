"""Deterministic V6 delivery assessment for conversational audio answers."""

from __future__ import annotations

from typing import Literal

from ..schemas.coach_conversation import (
    ConversationalRubricDimension,
    DeliveryObservation,
)
from .coach_attempt_pipeline import SpeechMetricsSnapshot
from .coach_text_spans import normalize_contract_text

Severity = Literal["none", "moderate", "material", "severe"]


def _pace(value: float) -> Severity:
    if value < 70 or value > 220:
        return "severe"
    if 70 <= value < 90 or 190 < value <= 220:
        return "material"
    if 90 <= value < 100 or 170 < value <= 190:
        return "moderate"
    return "none"


def _fillers(value: float) -> Severity:
    if value > 9:
        return "severe"
    if value > 6:
        return "material"
    if value > 3:
        return "moderate"
    return "none"


def _scaled_count(
    value: int,
    *,
    moderate_lower: float,
    moderate_upper: float,
    material_lower: float,
    material_upper: float,
) -> Severity:
    if value > material_upper:
        return "severe"
    if material_lower < value <= material_upper:
        return "material"
    if moderate_lower < value <= moderate_upper:
        return "moderate"
    return "none"


def _restarts(value: int) -> Severity:
    if value >= 8:
        return "severe"
    if value >= 5:
        return "material"
    if value >= 3:
        return "moderate"
    return "none"


def _observation(
    measured_value: int | float, threshold_bucket: str, severity: Severity
) -> DeliveryObservation:
    return DeliveryObservation(
        measured_value=measured_value,
        threshold_bucket=threshold_bucket,
        severity=severity,
    )


def _not_assessed() -> ConversationalRubricDimension:
    return ConversationalRubricDimension(level="not_assessed")


def assess_delivery(
    recording_type: Literal["text", "audio"],
    transcript: str,
    metrics: SpeechMetricsSnapshot | None,
) -> ConversationalRubricDimension:
    """Assess permitted speech metrics using the exact ordered V6 rules."""

    transcript_word_count = len(normalize_contract_text(transcript).split())
    if (
        recording_type == "text"
        or metrics is None
        or transcript_word_count < 40
        or metrics.duration_ms < 20_000
    ):
        return _not_assessed()

    duration_minutes = metrics.duration_ms / 60_000
    pause_moderate_lower = max(2, duration_minutes)
    pause_moderate_upper = max(3, 2 * duration_minutes)
    pause_material_lower = pause_moderate_upper
    pause_material_upper = max(6, 4 * duration_minutes)
    hedge_moderate_lower = max(2, metrics.word_count / 60)
    hedge_moderate_upper = max(4, metrics.word_count / 40)
    hedge_material_lower = hedge_moderate_upper
    hedge_material_upper = max(8, metrics.word_count / 20)

    observations = {
        "pace": _observation(
            metrics.words_per_minute,
            "wpm:70/90/100/170/190/220",
            _pace(metrics.words_per_minute),
        ),
        "fillers_per_minute": _observation(
            metrics.filler_rate_per_minute,
            "fillers_per_minute:3/6/9",
            _fillers(metrics.filler_rate_per_minute),
        ),
        "long_pauses": _observation(
            metrics.long_pause_count,
            (
                f"long_pauses:{pause_moderate_lower}/{pause_moderate_upper}/"
                f"{pause_material_upper}"
            ),
            _scaled_count(
                metrics.long_pause_count,
                moderate_lower=pause_moderate_lower,
                moderate_upper=pause_moderate_upper,
                material_lower=pause_material_lower,
                material_upper=pause_material_upper,
            ),
        ),
        "hedging": _observation(
            metrics.hedging_count,
            (
                f"hedging:{hedge_moderate_lower}/{hedge_moderate_upper}/"
                f"{hedge_material_upper}"
            ),
            _scaled_count(
                metrics.hedging_count,
                moderate_lower=hedge_moderate_lower,
                moderate_upper=hedge_moderate_upper,
                material_lower=hedge_material_lower,
                material_upper=hedge_material_upper,
            ),
        ),
    }
    if metrics.restart_count is not None:
        observations["restarts"] = _observation(
            metrics.restart_count,
            "restarts:3-4/5-7/8+",
            _restarts(metrics.restart_count),
        )

    severities = tuple(item.severity for item in observations.values())
    severe_count = severities.count("severe")
    material_count = severities.count("material")
    moderate_count = severities.count("moderate")
    if severe_count >= 1 or material_count >= 3:
        level = "needs_work"
    elif material_count == 2 or (material_count == 1 and moderate_count >= 2):
        level = "developing"
    elif material_count == 1 or (material_count == 0 and moderate_count >= 2):
        level = "interview_ready"
    else:
        level = "strong"
    return ConversationalRubricDimension(level=level, observations=observations)
