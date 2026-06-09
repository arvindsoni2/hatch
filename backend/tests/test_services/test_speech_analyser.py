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


# ── Timestamp-based delivery metrics (Phase A) ────────────────────────────────

def _make_words(
    texts: list[str], start: float = 0.0, word_dur: float = 0.2, gap: float = 0.1
) -> list[dict]:
    """Build uniform word-timestamp list with fixed duration and inter-word gap."""
    words = []
    t = start
    for text in texts:
        words.append({"w": text, "start": t, "end": t + word_dur})
        t += word_dur + gap
    return words


class TestSpeechAnalyserFromTimestamps:
    """Tests for analyse_from_timestamps() — deterministic delivery metrics."""

    def test_words_per_minute(self) -> None:
        """WPM = word_count / (last_end - first_start) * 60, within ±5 WPM of expected."""
        # 120 words, each 0.2 s long with 0.3 s gap → stride 0.5 s
        # total span: first_start=0, last_end = 119*0.5 + 0.2 = 59.7 s → ~121 WPM
        texts = ["word"] * 120
        words = _make_words(texts, word_dur=0.2, gap=0.3)
        analyser = SpeechAnalyserService()
        metrics = analyser.analyse_from_timestamps(" ".join(texts), words)
        assert abs(metrics.wpm - 120.0) < 10.0

    def test_filler_word_rate(self) -> None:
        """Filler rate is fillers-per-minute; custom locale list is used when supplied."""
        transcript = "um you know basically um like so"
        words = _make_words(transcript.split(), word_dur=0.3, gap=0.2)
        fillers = ["um", "you know", "basically", "like", "so"]
        analyser = SpeechAnalyserService()
        metrics = analyser.analyse_from_timestamps(transcript, words, locale_fillers=fillers)
        assert metrics.filler_count >= 4
        assert metrics.filler_rate > 0.0

    def test_filler_word_rate_uses_default_when_no_locale_fillers(self) -> None:
        """Without locale_fillers, the built-in English list is used as fallback."""
        transcript = "um uh basically like you know"
        words = _make_words(transcript.split())
        analyser = SpeechAnalyserService()
        metrics = analyser.analyse_from_timestamps(transcript, words)
        assert metrics.filler_count >= 4

    def test_long_pause_detection(self) -> None:
        """Gaps > 2 s between consecutive words are counted as long pauses."""
        words = [
            {"w": "I", "start": 0.0, "end": 0.2},
            {"w": "worked", "start": 0.4, "end": 0.8},
            # 3.2-second gap — long pause
            {"w": "on", "start": 4.0, "end": 4.2},
            {"w": "this", "start": 4.4, "end": 4.7},
            # 5.3-second gap — another long pause
            {"w": "project", "start": 10.0, "end": 10.5},
        ]
        analyser = SpeechAnalyserService()
        metrics = analyser.analyse_from_timestamps("I worked on this project", words)
        assert metrics.pause_count == 2

    def test_no_long_pauses_in_fluent_speech(self) -> None:
        """Normal inter-word gaps (< 2 s) are not counted as pauses."""
        texts = ["this", "is", "fluent", "speech"]
        words = _make_words(texts, gap=0.1)
        analyser = SpeechAnalyserService()
        metrics = analyser.analyse_from_timestamps(" ".join(texts), words)
        assert metrics.pause_count == 0

    def test_star_section_coverage_full(self) -> None:
        """A complete STAR answer (all four sections present) scores 1.0."""
        transcript = (
            "In my previous role I was working on a legacy migration project. "
            "My goal was to reduce downtime during deployment. "
            "So I implemented a blue-green deployment strategy with automated rollback. "
            "As a result we reduced deployment failures by 80%."
        )
        words = _make_words(transcript.split())
        analyser = SpeechAnalyserService()
        metrics = analyser.analyse_from_timestamps(transcript, words)
        assert metrics.star_coverage == pytest.approx(1.0)

    def test_star_section_coverage_partial(self) -> None:
        """An answer with only action + result sections scores 0 < coverage < 1.0."""
        transcript = "So I built the feature and as a result load time dropped by 50%."
        words = _make_words(transcript.split())
        analyser = SpeechAnalyserService()
        metrics = analyser.analyse_from_timestamps(transcript, words)
        assert 0.0 < metrics.star_coverage < 1.0

    def test_star_section_coverage_absent(self) -> None:
        """A vague, unstructured answer scores 0.0."""
        transcript = "It was a project and it went well."
        words = _make_words(transcript.split())
        analyser = SpeechAnalyserService()
        metrics = analyser.analyse_from_timestamps(transcript, words)
        assert metrics.star_coverage == 0.0

    def test_empty_words_returns_zero_metrics(self) -> None:
        """Empty words list returns default SpeechMetrics with all zeros."""
        analyser = SpeechAnalyserService()
        metrics = analyser.analyse_from_timestamps("", [])
        assert metrics.wpm == 0.0
        assert metrics.filler_count == 0
        assert metrics.pause_count == 0
        assert metrics.star_coverage == 0.0
