"""Voice emotion analyser — audeering wav2vec2 dimensional regression.

Returns continuous arousal / valence / dominance scores (all in [0, 1]).
Uses module-level optional import so names are patchable in tests; raises
a clear ImportError at instantiation time when transformers is absent.
"""
from __future__ import annotations

import logging

import numpy as np

from ..schemas.coach import VoiceToneResult

logger = logging.getLogger(__name__)

_MODEL_NAME = "audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim"

# audeering logit order: [arousal, dominance, valence]
_IDX_AROUSAL = 0
_IDX_DOMINANCE = 1
_IDX_VALENCE = 2

# Optional imports — set to None when transformers is not installed so that
# module import never fails. __init__ checks and raises with a helpful message.
try:
    from transformers import AutoModelForAudioClassification, AutoProcessor
except ImportError:  # pragma: no cover
    AutoProcessor = None  # type: ignore[assignment, misc]
    AutoModelForAudioClassification = None  # type: ignore[assignment, misc]


class AudeeringEmotionAnalyser:
    """Wraps the audeering wav2vec2 model for on-CPU dimensional emotion regression.

    Usage:
        analyser = AudeeringEmotionAnalyser(device="cpu")
        result = analyser.analyse(audio_array, sampling_rate=16_000)

    Args:
        model_name: HuggingFace model ID. Defaults to audeering dim-regression model.
        device: "cpu" or "cuda". Defaults to "cpu".
    """

    def __init__(
        self,
        model_name: str = _MODEL_NAME,
        device: str = "cpu",
    ) -> None:
        if AutoProcessor is None or AutoModelForAudioClassification is None:
            raise ImportError(
                "Voice emotion analysis requires 'transformers' and 'torch'. "
                "Run: pip install -r requirements-perception.txt"
            )

        logger.info("Loading voice emotion model %s on %s …", model_name, device)
        self._processor = AutoProcessor.from_pretrained(model_name)
        self._model = AutoModelForAudioClassification.from_pretrained(model_name)
        if device != "cpu":
            self._model = self._model.to(device)
        self._device = device
        logger.info("Voice emotion model loaded.")

    def analyse(self, audio: np.ndarray, sampling_rate: int = 16_000) -> VoiceToneResult:
        """Run dimensional emotion regression on a mono audio array.

        Args:
            audio: 1-D float32 numpy array at *sampling_rate* Hz.
            sampling_rate: Sample rate of *audio*. Must be 16 000 Hz for audeering.

        Returns:
            VoiceToneResult with arousal, valence, dominance each clamped to [0, 1].
        """
        if audio is None or len(audio) == 0:
            return VoiceToneResult()

        try:
            inputs = self._processor(
                audio,
                sampling_rate=sampling_rate,
                return_tensors="pt",
            )
            if self._device != "cpu":
                inputs = {k: v.to(self._device) for k, v in inputs.items()}

            output = self._model(**inputs)
            logits = output.logits.squeeze()  # shape: (3,) — [arousal, dominance, valence]

            # Use Python float conversion so no torch import needed at runtime here
            def _clamp(val: float) -> float:
                return max(0.0, min(1.0, float(val)))

            arousal = _clamp(logits[_IDX_AROUSAL])
            dominance = _clamp(logits[_IDX_DOMINANCE])
            valence = _clamp(logits[_IDX_VALENCE])

        except Exception as exc:
            logger.warning("Voice emotion analysis failed: %s — returning defaults", exc)
            return VoiceToneResult(sample_count=len(audio))

        return VoiceToneResult(
            arousal=round(arousal, 4),
            valence=round(valence, 4),
            dominance=round(dominance, 4),
            sample_count=len(audio),
        )
