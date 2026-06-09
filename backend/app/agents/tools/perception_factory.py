"""Provider-agnostic perception factory — mirrors the llm_factory pattern.

Agent and service code calls get_transcriber(), get_voice_emotion_analyser(),
get_face_analyser(), or get_tts(). The provider and model names come from
profile.yaml → perception so users swap between faster-whisper, Deepgram,
audeering, Piper, etc. without touching agent code.

Never import a specific perception provider directly in agent or service code.
Always go through this module.
"""
from __future__ import annotations

import logging
import os

from app._exceptions import PerceptionNotAvailableError
from .profile_loader import load_profile

logger = logging.getLogger(__name__)


def get_transcriber():
    """Return the configured ASR transcriber from profile.yaml → perception.asr.

    The transcriber implements Transcriber protocol:
        transcribe(audio_path: str) -> TranscriptionResult

    Raises:
        PerceptionNotAvailableError: if the configured provider is not installed.
    """
    profile = load_profile()
    cfg = profile.perception.asr

    if cfg.provider == "faster_whisper":
        from app.services.transcriber import FasterWhisperTranscriber  # noqa: PLC0415
        download_root = os.getenv("WHISPER_MODEL_CACHE") or None
        return FasterWhisperTranscriber(
            model_size=cfg.model,
            compute_type=cfg.compute_type,
            language=cfg.language,
            device="cpu",
            download_root=download_root,
        )

    if cfg.provider == "web_speech":
        from app.services.transcriber import WebSpeechPassthroughTranscriber  # noqa: PLC0415
        return WebSpeechPassthroughTranscriber()

    raise PerceptionNotAvailableError(
        f"ASR provider '{cfg.provider}' is not supported yet. "
        "Supported: faster_whisper, web_speech."
    )


def get_voice_emotion_analyser():
    """Return the configured voice emotion analyser from profile.yaml → perception.voice_emotion.

    Implements Phase B: audeering wav2vec2 dimensional regression on CPU.

    The analyser implements:
        analyse(audio: np.ndarray, sampling_rate: int) -> VoiceToneResult

    Raises:
        PerceptionNotAvailableError: if the provider is disabled or not installed.
    """
    profile = load_profile()
    cfg = profile.perception.voice_emotion

    if cfg.provider == "none":
        raise PerceptionNotAvailableError(
            "Voice emotion analysis is disabled (perception.voice_emotion.provider = 'none'). "
            "Set to 'audeering' and install requirements-perception.txt."
        )

    if cfg.provider == "audeering":
        try:
            from app.services.voice_emotion_analyser import AudeeringEmotionAnalyser  # noqa: PLC0415
        except ImportError as exc:
            raise PerceptionNotAvailableError(
                "audeering voice emotion requires 'transformers' and 'torch'. "
                "Run: pip install -r requirements-perception.txt"
            ) from exc
        return AudeeringEmotionAnalyser(model_name=cfg.model, device="cpu")

    raise PerceptionNotAvailableError(
        f"Voice emotion provider '{cfg.provider}' is not supported. "
        "Supported: audeering, none."
    )


def get_face_analyser():
    """Return the face/engagement analyser from profile.yaml → perception.face.

    Phase D implementation — MediaPipe runs in-browser; server-side is EmotiEffLib.
    Raises PerceptionNotAvailableError until Phase D is implemented.
    """
    profile = load_profile()
    cfg = profile.perception.face

    if not cfg.enabled:
        raise PerceptionNotAvailableError(
            "Face analysis is disabled (perception.face.enabled = false). "
            "Enable it in profile.yaml and accept the consent prompt."
        )

    raise PerceptionNotAvailableError(
        f"Face analyser provider '{cfg.provider}' is not implemented yet (Phase D)."
    )


def get_tts():
    """Return the TTS provider from profile.yaml → perception.tts.

    Phase E implementation. Raises PerceptionNotAvailableError until Phase E.
    """
    profile = load_profile()
    cfg = profile.perception.tts

    if cfg.provider == "none":
        raise PerceptionNotAvailableError(
            "TTS is disabled (perception.tts.provider = 'none'). "
            "Set to 'piper' and install piper-tts for Phase E."
        )

    raise PerceptionNotAvailableError(
        f"TTS provider '{cfg.provider}' is not implemented yet (Phase E)."
    )
