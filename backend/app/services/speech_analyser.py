"""Speech Analyser — pure Python analysis of transcript for filler words, WPM, hedging."""
from __future__ import annotations

import re

from ..schemas.coach import SpeechMetrics

# Filler words to detect (case-insensitive whole-word matches)
_FILLERS = [
    "um", "uh", "er", "ah", "hmm",
    "basically", "literally", "actually", "honestly",
    "you know", "right", "like", "so",
    "kind of", "sort of",
]

# Hedging phrases that weaken impact
_HEDGING = [
    "i think", "i believe", "i guess", "i suppose",
    "maybe", "perhaps", "probably", "possibly",
    "sort of", "kind of", "a bit", "slightly",
    "i'm not sure", "it might", "it could",
]

# Compiled patterns
_FILLER_PATTERNS = [re.compile(r"\b" + re.escape(f) + r"\b", re.IGNORECASE) for f in _FILLERS]
_HEDGING_PATTERNS = [re.compile(re.escape(h), re.IGNORECASE) for h in _HEDGING]


class SpeechAnalyserService:
    """Analyses transcripts for speech quality metrics. No Claude API required."""

    def analyse(self, transcript: str, duration_ms: int) -> SpeechMetrics:
        """Compute speech metrics from a transcript and duration.

        Args:
            transcript: Raw transcript text from STT.
            duration_ms: Answer duration in milliseconds.

        Returns:
            SpeechMetrics with filler count, WPM, hedging count, etc.
        """
        if not transcript.strip():
            return SpeechMetrics(duration_ms=duration_ms)

        # Filler count
        filler_count = sum(
            len(p.findall(transcript)) for p in _FILLER_PATTERNS
        )

        # Word count and WPM
        words = transcript.split()
        word_count = len(words)
        minutes = duration_ms / 60_000 if duration_ms > 0 else 1
        wpm = word_count / minutes if minutes > 0 else 0.0

        # Hedging count
        hedging_count = sum(
            len(p.findall(transcript)) for p in _HEDGING_PATTERNS
        )

        # Pause count: estimate from ellipses, long pauses indicated by "..."
        pause_count = transcript.count("...") + transcript.count("…")
        # Also count sentence-ending pauses as a proxy (periods followed by space)
        pause_count += len(re.findall(r"[.!?]\s", transcript))

        return SpeechMetrics(
            filler_count=filler_count,
            wpm=round(wpm, 1),
            hedging_count=hedging_count,
            duration_ms=duration_ms,
            pause_count=pause_count,
        )

    def get_filler_positions(self, transcript: str) -> list[dict]:
        """Return positions of filler words in the transcript for highlighting.

        Args:
            transcript: Raw transcript text.

        Returns:
            List of {word, start, end} dicts for UI highlighting.
        """
        positions: list[dict] = []
        for filler, pattern in zip(_FILLERS, _FILLER_PATTERNS):
            for match in pattern.finditer(transcript):
                positions.append({
                    "word": match.group(),
                    "start": match.start(),
                    "end": match.end(),
                })
        return sorted(positions, key=lambda x: x["start"])
