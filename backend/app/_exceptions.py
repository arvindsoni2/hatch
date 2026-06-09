"""Application-wide exception types shared across modules."""
from __future__ import annotations


class PerceptionNotAvailableError(RuntimeError):
    """Raised when a perception capability (ASR, TTS, etc.) is not installed or configured."""
