"""Tests for SpeechAnalyserService — filler counting, WPM, hedging detection."""
from __future__ import annotations

import pytest

from app.services.speech_analyser import SpeechAnalyserService
from app.schemas.coach import SpeechMetrics


@pytest.fixture()
def analyser() -> SpeechAnalyserService:
    return SpeechAnalyserService()


def test_filler_count_accuracy(analyser: SpeechAnalyserService) -> None:
    """Fillers 'um', 'uh', 'basically', 'literally', 'you know', 'like' are counted."""
    transcript = "Um, so I basically like went to the store, you know, and uh it was fine."
    # um=1, basically=1, like=1, you know=1, uh=1 → 5 fillers
    metrics = analyser.analyse(transcript, duration_ms=10_000)
    assert metrics.filler_count >= 4


def test_filler_count_clean_transcript(analyser: SpeechAnalyserService) -> None:
    """A clean, professional transcript should have zero or very low filler count."""
    transcript = (
        "In my previous role as Solutions Architect at a FTSE 100 company, "
        "I led the migration of 200 workloads to AWS, reducing TCO by 34%."
    )
    metrics = analyser.analyse(transcript, duration_ms=20_000)
    assert metrics.filler_count == 0


def test_wpm_calculation(analyser: SpeechAnalyserService) -> None:
    """WPM = word_count / (duration_ms / 60000). Verify within ±5 WPM."""
    transcript = " ".join(["word"] * 120)  # 120 words
    duration_ms = 60_000  # 1 minute → expected 120 WPM
    metrics = analyser.analyse(transcript, duration_ms=duration_ms)
    assert abs(metrics.wpm - 120.0) < 5.0


def test_wpm_zero_duration(analyser: SpeechAnalyserService) -> None:
    """Zero duration should not raise; service falls back to 1-minute denominator."""
    metrics = analyser.analyse("some words here", duration_ms=0)
    assert metrics.wpm >= 0.0  # no crash; value is word_count (fallback minutes=1)


def test_hedging_detection(analyser: SpeechAnalyserService) -> None:
    """Hedging phrases like 'I think', 'maybe', 'perhaps', 'sort of' are counted."""
    transcript = "I think this is correct. Maybe we could try something else. I believe it sort of worked."
    metrics = analyser.analyse(transcript, duration_ms=15_000)
    assert metrics.hedging_count >= 3


def test_duration_stored(analyser: SpeechAnalyserService) -> None:
    """duration_ms is stored as-is in SpeechMetrics."""
    metrics = analyser.analyse("Hello world", duration_ms=45_000)
    assert metrics.duration_ms == 45_000


def test_filler_positions_returned(analyser: SpeechAnalyserService) -> None:
    """get_filler_positions returns a list of dicts with 'word', 'start', 'end' keys."""
    transcript = "Um, I basically just did it."
    positions = analyser.get_filler_positions(transcript)
    assert isinstance(positions, list)
    assert len(positions) >= 2
    for p in positions:
        assert "word" in p
        assert "start" in p
        assert "end" in p


def test_returns_speech_metrics_type(analyser: SpeechAnalyserService) -> None:
    """analyse() always returns a SpeechMetrics instance."""
    result = analyser.analyse("Any transcript text here.", duration_ms=5000)
    assert isinstance(result, SpeechMetrics)
