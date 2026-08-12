"""Speech Analyser — pure Python analysis of transcript for filler words, WPM, hedging.

Two analysis paths:
  analyse(transcript, duration_ms)              — text-only path (Web Speech / typed)
  analyse_from_timestamps(transcript, words)    — timestamp path (faster-whisper)

The timestamp path is more accurate: WPM uses actual spoken duration, pauses are
detected from real gaps between words, and filler rate is per-minute rather than a
raw count. Always prefer analyse_from_timestamps when word timestamps are available.
"""
from __future__ import annotations

import re

from ..schemas.coach import SpeechMetrics

# ── Default English filler list (used when no locale pack is provided) ────────
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

# Compiled patterns (default English list only)
_FILLER_PATTERNS = [re.compile(r"\b" + re.escape(f) + r"\b", re.IGNORECASE) for f in _FILLERS]
_HEDGING_PATTERNS = [re.compile(re.escape(h), re.IGNORECASE) for h in _HEDGING]

# Gaps wider than this (seconds) between consecutive words are counted as long pauses.
_LONG_PAUSE_THRESHOLD_S: float = 2.0

# STAR section keyword patterns — each section is detected by at least one match.
_STAR_PATTERNS: dict[str, list[str]] = {
    "situation": [
        r"\b(?:i was (?:working|responsible|dealing|managing|leading|tasked|part of))\b",
        r"\bin my (?:previous|former|last|current) (?:role|job|position|company)\b",
        r"\b(?:at (?:the time|that point)|when i (?:joined|started|was at))\b",
        r"\b(?:we were (?:working|building|running|facing|dealing))\b",
        r"\b(?:there was a (?:situation|challenge|problem|issue|project))\b",
        r"\b(?:i had been|we had been) (?:working|building|running)\b",
    ],
    "task": [
        r"\b(?:i was (?:tasked|asked|responsible|given))\b",
        r"\b(?:my (?:goal|role|job|task|objective|responsibility) was)\b",
        r"\b(?:the challenge (?:was|involved))\b",
        r"\b(?:needed to|had to (?:ensure|deliver|build|create|fix|resolve))\b",
    ],
    "action": [
        r"\b(?:so i|i (?:decided|started|began|worked|implemented|built|designed|created|led|managed|reached out))\b",
        r"\b(?:i then|first i|my approach|what i did)\b",
        r"\b(?:to (?:address|resolve|fix|tackle|solve))\b",
        r"\b(?:i collaborated|i partnered|i coordinated)\b",
    ],
    "result": [
        r"\b(?:as a result|this (?:resulted|led|meant))\b",
        r"\b(?:we (?:achieved|delivered|reduced|increased|saved|improved))\b",
        r"\b(?:i (?:achieved|delivered|reduced|increased|saved|improved))\b",
        r"\b(?:the outcome|in the end|ultimately|by the end)\b",
        r"\b(?:this (?:helped|enabled|allowed)|(?:reduced|increased|saved|improved) (?:by|\d))\b",
    ],
}


def _compute_star_coverage(transcript: str) -> float:
    """Return fraction [0.0–1.0] of STAR sections detected in *transcript*."""
    lower = transcript.lower()
    hits = sum(
        1 for section_patterns in _STAR_PATTERNS.values()
        if any(re.search(p, lower) for p in section_patterns)
    )
    return round(hits / 4, 2)


class SpeechAnalyserService:
    """Analyses transcripts for speech quality metrics. No LLM or API required."""

    # ── Text-only path (Web Speech / typed transcript) ──────────────────────

    def analyse(self, transcript: str, duration_ms: int) -> SpeechMetrics:
        """Compute speech metrics from a transcript and duration.

        Use this for text-mode answers where no word timestamps are available.
        Prefer analyse_from_timestamps() when faster-whisper word timestamps exist.

        Args:
            transcript: Raw transcript text from STT or typed input.
            duration_ms: Answer duration in milliseconds.

        Returns:
            SpeechMetrics with filler count, WPM, hedging count, etc.
        """
        if not transcript.strip():
            return SpeechMetrics(duration_ms=duration_ms)

        filler_count = sum(len(p.findall(transcript)) for p in _FILLER_PATTERNS)

        words = transcript.split()
        word_count = len(words)
        minutes = duration_ms / 60_000 if duration_ms > 0 else 1
        wpm = word_count / minutes if minutes > 0 else 0.0

        hedging_count = sum(len(p.findall(transcript)) for p in _HEDGING_PATTERNS)

        pause_count = transcript.count("...") + transcript.count("…")
        pause_count += len(re.findall(r"[.!?]\s", transcript))

        star_coverage = _compute_star_coverage(transcript)

        return SpeechMetrics(
            filler_count=filler_count,
            wpm=round(wpm, 1),
            hedging_count=hedging_count,
            duration_ms=duration_ms,
            pause_count=pause_count,
            star_coverage=star_coverage,
        )

    def analyse_conversational_v1(
        self,
        transcript: str,
        *,
        duration_ms: int,
        words: list[dict] | None = None,
    ) -> dict[str, int | float | None]:
        """Project delivery analysis to the V6 conversational allow-list.

        STAR coverage and any voice/video analysis are intentionally excluded:
        they are not observable fields in the conversational-v1 contract.
        """
        if words:
            metrics = self.analyse_from_timestamps(transcript, words)
            word_count = len(words)
            long_pause_count: int | None = metrics.pause_count
        else:
            metrics = self.analyse(transcript, duration_ms)
            word_count = len(transcript.split())
            long_pause_count = None
        return {
            "duration_ms": metrics.duration_ms,
            "word_count": word_count,
            "words_per_minute": metrics.wpm,
            "filler_count": metrics.filler_count,
            "filler_rate_per_minute": metrics.filler_rate,
            "hedging_count": metrics.hedging_count,
            "pause_count": metrics.pause_count,
            "long_pause_count": long_pause_count,
        }

    # ── Timestamp path (faster-whisper word timestamps) ──────────────────────

    def analyse_from_timestamps(
        self,
        transcript: str,
        words: list[dict],
        locale_fillers: list[str] | None = None,
    ) -> SpeechMetrics:
        """Compute delivery metrics from transcript + word timestamps from ASR.

        This is more accurate than analyse(): WPM uses actual spoken duration,
        pauses are detected from real timing gaps, and filler rate is normalised
        per minute rather than a raw count.

        Args:
            transcript: Raw transcript text from ASR output.
            words: Word timestamps from ASR: list of {w, start, end} dicts.
            locale_fillers: Optional locale-specific filler list from the locale pack's
                coach.fillers key. Falls back to the default English list when None.

        Returns:
            SpeechMetrics with accurate wpm, filler_rate, pause_count, star_coverage.
        """
        if not transcript.strip() or not words:
            return SpeechMetrics()

        fillers = locale_fillers if locale_fillers is not None else _FILLERS
        filler_patterns = [
            re.compile(r"\b" + re.escape(f) + r"\b", re.IGNORECASE) for f in fillers
        ]

        # Duration from actual word timestamps
        duration_s = words[-1]["end"] - words[0]["start"]
        duration_ms = int(duration_s * 1000)
        minutes = duration_s / 60.0 if duration_s > 0 else 1.0

        # WPM from actual word count / real spoken duration
        wpm = len(words) / minutes

        # Filler count and per-minute rate
        filler_count = sum(len(p.findall(transcript)) for p in filler_patterns)
        filler_rate = round(filler_count / minutes, 2)

        # Long pause detection: gaps between consecutive word timestamps
        pause_count = sum(
            1 for i in range(1, len(words))
            if (words[i]["start"] - words[i - 1]["end"]) > _LONG_PAUSE_THRESHOLD_S
        )

        hedging_count = sum(len(p.findall(transcript)) for p in _HEDGING_PATTERNS)

        star_coverage = _compute_star_coverage(transcript)

        return SpeechMetrics(
            filler_count=filler_count,
            filler_rate=filler_rate,
            wpm=round(wpm, 1),
            hedging_count=hedging_count,
            duration_ms=duration_ms,
            pause_count=pause_count,
            star_coverage=star_coverage,
        )

    def get_filler_positions(self, transcript: str) -> list[dict]:
        """Return positions of filler words in the transcript for UI highlighting.

        Args:
            transcript: Raw transcript text.

        Returns:
            List of {word, start, end} dicts sorted by position.
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
