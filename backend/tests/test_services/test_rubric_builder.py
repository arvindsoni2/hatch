"""Tests for rubric_builder — deterministic delivery/tone dimensions + content mapping."""
from __future__ import annotations

import pytest

from app.schemas.coach import (
    AnswerEvaluation,
    RubricDimension,
    SessionRubric,
    SpeechMetrics,
    VoiceToneResult,
)
from app.services.rubric_builder import (
    CONTENT_DIMENSIONS,
    build_content_dimensions,
    build_delivery_dimension,
    build_rubric,
    build_tone_dimension,
    score_to_band,
)


# ---------------------------------------------------------------------------
# score_to_band
# ---------------------------------------------------------------------------

class TestScoreToBand:
    @pytest.mark.parametrize("score,expected_band", [
        (10, "strong"), (8, "strong"),
        (7, "good"),    (6, "good"),
        (5, "needs_work"), (4, "needs_work"),
        (3, "weak"),    (0, "weak"),
    ])
    def test_band_thresholds(self, score: int, expected_band: str) -> None:
        assert score_to_band(score) == expected_band


# ---------------------------------------------------------------------------
# build_delivery_dimension
# ---------------------------------------------------------------------------

class TestBuildDeliveryDimension:

    def test_returns_rubric_dimension(self) -> None:
        metrics = SpeechMetrics(wpm=145.0, filler_count=2, pause_count=1, duration_ms=60_000)
        dim = build_delivery_dimension(metrics)
        assert isinstance(dim, RubricDimension)

    def test_evidence_mentions_wpm(self) -> None:
        metrics = SpeechMetrics(wpm=160.0, filler_count=0, pause_count=0, duration_ms=30_000)
        dim = build_delivery_dimension(metrics)
        combined = " ".join(dim.evidence).lower()
        assert "wpm" in combined or "words per minute" in combined or "160" in combined

    def test_high_filler_count_reflected_in_evidence(self) -> None:
        metrics = SpeechMetrics(wpm=140.0, filler_count=12, pause_count=0, duration_ms=60_000)
        dim = build_delivery_dimension(metrics)
        combined = " ".join(dim.evidence).lower()
        assert "filler" in combined or "12" in combined

    def test_ideal_pace_scores_strong(self) -> None:
        """130-160 WPM, 0 fillers, 0 long pauses → strong."""
        metrics = SpeechMetrics(wpm=145.0, filler_count=0, pause_count=0, duration_ms=60_000)
        dim = build_delivery_dimension(metrics)
        assert dim.score_band in ("strong", "good")

    def test_excessive_fillers_scores_weak(self) -> None:
        metrics = SpeechMetrics(wpm=140.0, filler_count=20, pause_count=0, duration_ms=60_000)
        dim = build_delivery_dimension(metrics)
        assert dim.score_band in ("weak", "needs_work")

    def test_drill_is_non_empty(self) -> None:
        metrics = SpeechMetrics(wpm=140.0, filler_count=3, pause_count=1, duration_ms=45_000)
        dim = build_delivery_dimension(metrics)
        assert dim.drill.strip() != ""


# ---------------------------------------------------------------------------
# build_tone_dimension
# ---------------------------------------------------------------------------

class TestBuildToneDimension:

    def test_returns_rubric_dimension(self) -> None:
        tone = VoiceToneResult(arousal=0.6, valence=0.5, dominance=0.7)
        dim = build_tone_dimension(tone)
        assert isinstance(dim, RubricDimension)

    def test_high_dominance_scores_well(self) -> None:
        """High dominance (> 0.6) + moderate arousal → good or strong band."""
        tone = VoiceToneResult(arousal=0.65, valence=0.55, dominance=0.75)
        dim = build_tone_dimension(tone)
        assert dim.score_band in ("strong", "good")

    def test_low_dominance_scores_poorly(self) -> None:
        """Very low dominance (< 0.25) → needs_work or weak."""
        tone = VoiceToneResult(arousal=0.2, valence=0.3, dominance=0.15)
        dim = build_tone_dimension(tone)
        assert dim.score_band in ("needs_work", "weak")

    def test_evidence_mentions_energy_or_confidence(self) -> None:
        tone = VoiceToneResult(arousal=0.7, valence=0.6, dominance=0.8)
        dim = build_tone_dimension(tone)
        combined = " ".join(dim.evidence).lower()
        assert any(word in combined for word in ("energy", "confidence", "assertive", "dominance", "arousal"))

    def test_drill_is_non_empty(self) -> None:
        tone = VoiceToneResult(arousal=0.4, valence=0.4, dominance=0.3)
        dim = build_tone_dimension(tone)
        assert dim.drill.strip() != ""


# ---------------------------------------------------------------------------
# build_content_dimensions
# ---------------------------------------------------------------------------

class TestBuildContentDimensions:

    def _make_eval(self, score: int = 7) -> AnswerEvaluation:
        return AnswerEvaluation(
            scores={d: score for d in CONTENT_DIMENSIONS},
            overall=float(score),
            feedback="Test feedback",
            strengths=["Clear structure"],
            improvements=["Add more examples"],
        )

    def test_returns_all_content_dimensions(self) -> None:
        dims = build_content_dimensions(self._make_eval())
        assert set(dims.keys()) == set(CONTENT_DIMENSIONS)

    def test_each_dimension_has_evidence(self) -> None:
        dims = build_content_dimensions(self._make_eval(score=8))
        for name, dim in dims.items():
            assert isinstance(dim.evidence, list), f"{name} evidence not a list"
            assert len(dim.evidence) >= 1, f"{name} evidence is empty"

    def test_each_dimension_has_drill(self) -> None:
        dims = build_content_dimensions(self._make_eval(score=4))
        for name, dim in dims.items():
            assert dim.drill.strip() != "", f"{name} drill is empty"

    def test_score_band_matches_score(self) -> None:
        dims = build_content_dimensions(self._make_eval(score=9))
        for dim in dims.values():
            assert dim.score_band == "strong"

    def test_low_score_produces_needs_work_band(self) -> None:
        dims = build_content_dimensions(self._make_eval(score=3))
        for dim in dims.values():
            assert dim.score_band in ("weak", "needs_work")


# ---------------------------------------------------------------------------
# build_rubric (integration)
# ---------------------------------------------------------------------------

class TestBuildRubric:

    def _good_eval(self) -> AnswerEvaluation:
        return AnswerEvaluation(
            scores={d: 8 for d in CONTENT_DIMENSIONS},
            overall=8.0,
            feedback="Good answer",
            strengths=["STAR structure clear"],
            improvements=["Quantify outcomes"],
        )

    def test_returns_session_rubric(self) -> None:
        rubric = build_rubric(self._good_eval())
        assert isinstance(rubric, SessionRubric)

    def test_content_dimensions_always_present(self) -> None:
        rubric = build_rubric(self._good_eval())
        for dim_name in CONTENT_DIMENSIONS:
            assert dim_name in rubric.dimensions, f"Missing dimension: {dim_name}"

    def test_delivery_present_with_speech_metrics(self) -> None:
        metrics = SpeechMetrics(wpm=145.0, filler_count=2, pause_count=1, duration_ms=60_000)
        rubric = build_rubric(self._good_eval(), speech_metrics=metrics)
        assert "delivery" in rubric.dimensions

    def test_delivery_absent_without_speech_metrics(self) -> None:
        rubric = build_rubric(self._good_eval(), speech_metrics=None)
        assert "delivery" not in rubric.dimensions

    def test_vocal_confidence_present_with_tone(self) -> None:
        tone = VoiceToneResult(arousal=0.6, valence=0.5, dominance=0.7)
        rubric = build_rubric(self._good_eval(), tone_result=tone)
        assert "vocal_confidence" in rubric.dimensions

    def test_vocal_confidence_absent_without_tone(self) -> None:
        rubric = build_rubric(self._good_eval(), tone_result=None)
        assert "vocal_confidence" not in rubric.dimensions

    def test_presence_absent_without_face_data(self) -> None:
        """presence dimension is NEVER added without face data — omit, don't zero."""
        rubric = build_rubric(self._good_eval())
        assert "presence" not in rubric.dimensions

    def test_focus_for_next_session_non_empty(self) -> None:
        rubric = build_rubric(self._good_eval())
        assert rubric.focus_for_next_session.strip() != ""

    def test_all_dimensions_have_evidence_list(self) -> None:
        metrics = SpeechMetrics(wpm=140.0, filler_count=3, pause_count=1, duration_ms=60_000)
        tone = VoiceToneResult(arousal=0.5, valence=0.4, dominance=0.6)
        rubric = build_rubric(self._good_eval(), speech_metrics=metrics, tone_result=tone)
        for name, dim in rubric.dimensions.items():
            assert isinstance(dim.evidence, list), f"{name}: evidence not a list"
            assert len(dim.evidence) >= 1, f"{name}: evidence is empty"
