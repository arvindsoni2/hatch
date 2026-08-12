from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.coach_conversation import ConversationalRubricDimension
from app.services.coach_attempt_pipeline import SpeechMetricsSnapshot
from app.services.coach_delivery_policy import assess_delivery


WORDS_80 = " ".join(f"word{index}" for index in range(80))


def metrics(
    *,
    wpm: float = 120,
    duration_ms: int = 60_000,
    word_count: int = 80,
    filler_rate: float = 0,
    hedging_count: int = 0,
    long_pause_count: int = 0,
    restart_count: int | None = None,
) -> SpeechMetricsSnapshot:
    return SpeechMetricsSnapshot(
        duration_ms=duration_ms,
        word_count=word_count,
        words_per_minute=wpm,
        filler_count=0,
        filler_rate_per_minute=filler_rate,
        hedging_count=hedging_count,
        pause_count=long_pause_count,
        long_pause_count=long_pause_count,
        restart_count=restart_count,
    )


@pytest.mark.parametrize(
    ("wpm", "expected"),
    [
        (69.99, "severe"),
        (70, "material"),
        (90, "moderate"),
        (100, "none"),
        (170, "none"),
        (190, "moderate"),
        (220, "material"),
        (220.01, "severe"),
    ],
)
def test_pace_equality_boundaries(wpm: float, expected: str) -> None:
    result = assess_delivery(
        "audio", WORDS_80, metrics(wpm=wpm, duration_ms=60_000)
    )

    assert result.observations["pace"].severity == expected


@pytest.mark.parametrize(
    ("filler_rate", "expected"),
    [(3, "none"), (3.01, "moderate"), (6, "moderate"), (6.01, "material"), (9, "material"), (9.01, "severe")],
)
def test_filler_rate_equality_boundaries(
    filler_rate: float, expected: str
) -> None:
    result = assess_delivery("audio", WORDS_80, metrics(filler_rate=filler_rate))

    assert result.observations["fillers_per_minute"].severity == expected


@pytest.mark.parametrize(
    ("long_pauses", "expected"),
    [(2, "none"), (3, "moderate"), (6, "material"), (7, "severe")],
)
def test_long_pause_uses_unrounded_duration_thresholds(
    long_pauses: int, expected: str
) -> None:
    result = assess_delivery(
        "audio",
        WORDS_80,
        metrics(duration_ms=90_000, long_pause_count=long_pauses),
    )

    assert result.observations["long_pauses"].severity == expected


@pytest.mark.parametrize(
    ("hedges", "expected"),
    [(2, "none"), (4, "moderate"), (8, "material"), (9, "severe")],
)
def test_hedging_uses_unrounded_word_count_thresholds(
    hedges: int, expected: str
) -> None:
    result = assess_delivery(
        "audio", WORDS_80, metrics(word_count=120, hedging_count=hedges)
    )

    assert result.observations["hedging"].severity == expected


def test_typed_short_audio_and_missing_metrics_are_not_assessed() -> None:
    assert assess_delivery("text", WORDS_80, None).level == "not_assessed"
    assert (
        assess_delivery("audio", "too short", metrics(duration_ms=19_999)).level
        == "not_assessed"
    )
    assert assess_delivery("audio", WORDS_80, None).level == "not_assessed"


def test_delivery_schema_rejects_prohibited_metric_families() -> None:
    with pytest.raises(ValidationError):
        ConversationalRubricDimension.model_validate(
            {
                "level": "strong",
                "observations": {
                    "vocal_confidence": {
                        "measured_value": 0.9,
                        "threshold_bucket": "prohibited",
                        "severity": "none",
                    }
                },
            }
        )


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"wpm": 221}, "needs_work"),
        ({"filler_rate": 7, "long_pause_count": 4, "hedging_count": 5}, "needs_work"),
        ({"filler_rate": 7, "long_pause_count": 4}, "developing"),
        ({"filler_rate": 7}, "interview_ready"),
        ({"filler_rate": 4}, "strong"),
    ],
)
def test_delivery_level_uses_first_matching_count_rule(
    overrides: dict[str, float | int], expected: str
) -> None:
    result = assess_delivery("audio", WORDS_80, metrics(**overrides))

    assert result.level == expected
