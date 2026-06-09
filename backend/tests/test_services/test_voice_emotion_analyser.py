"""Tests for AudeeringEmotionAnalyser — arousal/valence/dominance, 16kHz mono, CPU.

torch is NOT installed in the local dev env (Docker-only dep), so we mock
the model output as a plain MagicMock that mimics tensor squeeze behaviour.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.schemas.coach import VoiceToneResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_audio(duration_s: float = 1.0, sr: int = 16_000) -> np.ndarray:
    """Return a mono 16kHz float32 sine-wave fixture."""
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    return (np.sin(2 * np.pi * 440 * t)).astype(np.float32)


def _mock_logits(arousal: float, dominance: float, valence: float) -> MagicMock:
    """Mock that mimics tensor.squeeze() returning [arousal, dominance, valence]."""
    squeezed = MagicMock()
    # __getitem__ gives back a MagicMock whose float() conversion returns the value
    squeezed.__getitem__ = lambda self, idx: [arousal, dominance, valence][idx]
    logits_mock = MagicMock()
    logits_mock.squeeze.return_value = squeezed
    out_mock = MagicMock()
    out_mock.logits = logits_mock
    return out_mock


def _build_analyser(arousal: float = 0.6, valence: float = 0.5, dominance: float = 0.7):
    """Instantiate AudeeringEmotionAnalyser with fully mocked model + processor."""
    with patch("app.services.voice_emotion_analyser.AutoProcessor") as MockProc, \
         patch("app.services.voice_emotion_analyser.AutoModelForAudioClassification") as MockModel:

        MockProc.from_pretrained.return_value = MagicMock()
        mock_model_inst = MagicMock(return_value=_mock_logits(arousal, dominance, valence))
        MockModel.from_pretrained.return_value = mock_model_inst

        from app.services.voice_emotion_analyser import AudeeringEmotionAnalyser  # noqa: PLC0415
        analyser = AudeeringEmotionAnalyser(device="cpu")

    # Keep reference so tests can override model behaviour after construction
    analyser._model = mock_model_inst
    return analyser


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAudeeringEmotionAnalyser:

    def test_returns_arousal_valence_dominance_in_range(self):
        """analyse() returns VoiceToneResult with all three values in [0, 1]."""
        analyser = _build_analyser(arousal=0.6, valence=0.4, dominance=0.7)
        audio = _make_audio(1.0)

        result = analyser.analyse(audio, sampling_rate=16_000)

        assert isinstance(result, VoiceToneResult)
        assert 0.0 <= result.arousal <= 1.0
        assert 0.0 <= result.valence <= 1.0
        assert 0.0 <= result.dominance <= 1.0

    def test_values_match_model_output(self):
        """analyse() maps model [arousal, dominance, valence] output correctly."""
        analyser = _build_analyser(arousal=0.8, valence=0.3, dominance=0.9)
        audio = _make_audio(2.0)

        result = analyser.analyse(audio, sampling_rate=16_000)

        assert abs(result.arousal - 0.8) < 0.01
        assert abs(result.valence - 0.3) < 0.01
        assert abs(result.dominance - 0.9) < 0.01

    def test_handles_16khz_mono_audio(self):
        """analyse() accepts 16kHz mono float32 numpy array without error."""
        analyser = _build_analyser()
        audio = _make_audio(3.0, sr=16_000)
        assert audio.ndim == 1, "fixture must be mono (1-D)"

        result = analyser.analyse(audio, sampling_rate=16_000)
        assert isinstance(result, VoiceToneResult)

    def test_sample_count_reflects_input_length(self):
        """sample_count in result equals len(audio)."""
        analyser = _build_analyser()
        audio = _make_audio(1.0, sr=16_000)

        result = analyser.analyse(audio, sampling_rate=16_000)
        assert result.sample_count == len(audio)

    def test_loads_with_device_cpu(self):
        """AudeeringEmotionAnalyser initialises without error when device='cpu'."""
        with patch("app.services.voice_emotion_analyser.AutoProcessor") as MockProc, \
             patch("app.services.voice_emotion_analyser.AutoModelForAudioClassification") as MockModel:

            MockProc.from_pretrained.return_value = MagicMock()
            MockModel.from_pretrained.return_value = MagicMock()

            from app.services.voice_emotion_analyser import AudeeringEmotionAnalyser  # noqa: PLC0415
            analyser = AudeeringEmotionAnalyser(device="cpu")

        assert analyser is not None

    def test_values_clamped_to_unit_interval(self):
        """Values outside [0,1] from the model are clamped by Python min/max."""
        analyser = _build_analyser()

        # Override model to return out-of-range values: a=−0.1, d=1.2, v=0.5
        bad_logits = MagicMock()
        squeezed = MagicMock()
        squeezed.__getitem__ = lambda self, idx: [-0.1, 1.2, 0.5][idx]
        bad_logits.logits.squeeze.return_value = squeezed
        analyser._model = MagicMock(return_value=bad_logits)

        audio = _make_audio(1.0)
        result = analyser.analyse(audio, sampling_rate=16_000)

        assert result.arousal >= 0.0
        assert result.dominance <= 1.0

    def test_empty_audio_returns_default(self):
        """Zero-length audio returns VoiceToneResult with all zeros, no crash."""
        analyser = _build_analyser()
        audio = np.array([], dtype=np.float32)

        result = analyser.analyse(audio, sampling_rate=16_000)
        assert isinstance(result, VoiceToneResult)
        assert result.arousal == 0.0
        assert result.valence == 0.0
        assert result.dominance == 0.0
        assert result.sample_count == 0
