"""Transcription service — wraps ASR provider implementations behind a unified interface.

Never import a specific ASR provider directly in agent or router code.
Always go through perception_factory.get_transcriber() instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import runtime_checkable, Protocol

# Module-level reference for easier mocking in tests.
# Set to None when faster-whisper is not installed; perception_factory raises a
# clear PerceptionNotAvailableError before anything tries to instantiate the model.
try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None  # type: ignore[assignment,misc]


# ── Public types ──────────────────────────────────────────────────────────────

@dataclass
class WordTimestamp:
    w: str
    start: float
    end: float


@dataclass
class TranscriptionResult:
    text: str
    language: str
    words: list[WordTimestamp] = field(default_factory=list)


@runtime_checkable
class Transcriber(Protocol):
    """Minimal interface that all transcriber implementations must satisfy."""

    def transcribe(self, audio_path: str) -> TranscriptionResult: ...


# ── faster-whisper implementation ─────────────────────────────────────────────

class FasterWhisperTranscriber:
    """Transcriber backed by faster-whisper (CTranslate2, CPU int8 by default).

    Model is lazy-loaded on the first transcribe() call to keep startup fast
    and to allow the module to import even when faster-whisper is not installed.
    """

    def __init__(
        self,
        model_size: str = "small",
        compute_type: str = "int8",
        language: str = "auto",
        device: str = "cpu",
        download_root: str | None = None,
    ) -> None:
        self._model_size = model_size
        self._compute_type = compute_type
        self._language: str | None = None if language == "auto" else language
        self._device = device
        self._download_root = download_root
        self._model = None

    def _load_model(self):
        if self._model is None:
            if WhisperModel is None:
                from app._exceptions import PerceptionNotAvailableError  # noqa: PLC0415
                raise PerceptionNotAvailableError(
                    "faster-whisper is not installed. "
                    "Install it with: pip install faster-whisper"
                )
            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
                download_root=self._download_root,
            )
        return self._model

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        model = self._load_model()
        segments, info = model.transcribe(
            audio_path,
            language=self._language,
            word_timestamps=True,
            vad_filter=True,
        )

        words: list[WordTimestamp] = []
        text_parts: list[str] = []

        for segment in segments:
            part = segment.text.strip()
            if part:
                text_parts.append(part)
            if segment.words:
                for w in segment.words:
                    words.append(WordTimestamp(
                        w=w.word.strip(),
                        start=float(w.start),
                        end=float(w.end),
                    ))

        return TranscriptionResult(
            text=" ".join(text_parts),
            language=info.language,
            words=words,
        )


# ── Web Speech pass-through (browser-side, no server ASR) ─────────────────────

class WebSpeechPassthroughTranscriber:
    """No-op transcriber — the client already ran Web Speech API and sends the transcript."""

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        raise NotImplementedError(
            "WebSpeechPassthroughTranscriber does not process audio files. "
            "The client sends the transcript directly via submit-answer."
        )
