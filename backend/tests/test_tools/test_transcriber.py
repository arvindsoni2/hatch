"""Tests for FasterWhisperTranscriber — unit tests mock the model to avoid ~240 MB download."""
from __future__ import annotations

import struct
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.transcriber import FasterWhisperTranscriber, TranscriptionResult, WordTimestamp


# ── WAV fixture ───────────────────────────────────────────────────────────────

def _make_silent_wav(tmp_path: Path, duration_s: float = 1.0, sample_rate: int = 16_000) -> Path:
    """Write a short silent mono WAV to *tmp_path* and return its path."""
    path = tmp_path / "fixture.wav"
    n_frames = int(duration_s * sample_rate)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(struct.pack(f"<{n_frames}h", *([0] * n_frames)))
    return path


# ── Mock helpers ──────────────────────────────────────────────────────────────

def _make_mock_word(word: str, start: float, end: float) -> MagicMock:
    w = MagicMock()
    w.word = word
    w.start = start
    w.end = end
    return w


def _make_mock_segment(text: str, words: list) -> MagicMock:
    seg = MagicMock()
    seg.text = text
    seg.words = words
    return seg


def _make_mock_info(language: str = "en") -> MagicMock:
    info = MagicMock()
    info.language = language
    return info


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestFasterWhisperTranscriber:

    def _make_transcriber(
        self,
        model_size: str = "small",
        compute_type: str = "int8",
        language: str = "auto",
        device: str = "cpu",
    ) -> FasterWhisperTranscriber:
        return FasterWhisperTranscriber(
            model_size=model_size,
            compute_type=compute_type,
            language=language,
            device=device,
        )

    def test_transcribe_returns_text_and_word_timestamps(self, tmp_path: Path) -> None:
        """transcribe() returns TranscriptionResult with non-empty text and word timestamps."""
        wav = _make_silent_wav(tmp_path)
        mock_words = [
            _make_mock_word("hello", 0.0, 0.5),
            _make_mock_word("world", 0.6, 1.0),
        ]
        mock_segment = _make_mock_segment("hello world", mock_words)
        mock_info = _make_mock_info("en")

        with patch("app.services.transcriber.WhisperModel") as MockModel:
            MockModel.return_value.transcribe.return_value = ([mock_segment], mock_info)
            t = self._make_transcriber()
            result = t.transcribe(str(wav))

        assert isinstance(result, TranscriptionResult)
        assert len(result.text) > 0
        assert len(result.words) == 2
        assert result.words[0].w == "hello"
        assert result.words[0].start == pytest.approx(0.0)
        assert result.words[0].end == pytest.approx(0.5)
        assert result.words[1].w == "world"
        assert result.words[1].start == pytest.approx(0.6)

    def test_language_autodetect(self, tmp_path: Path) -> None:
        """Language detected by the model is returned in TranscriptionResult.language."""
        wav = _make_silent_wav(tmp_path)
        mock_info = _make_mock_info("fr")

        with patch("app.services.transcriber.WhisperModel") as MockModel:
            MockModel.return_value.transcribe.return_value = ([], mock_info)
            t = self._make_transcriber(language="auto")
            result = t.transcribe(str(wav))

        assert result.language == "fr"

    def test_int8_model_loads_on_cpu(self, tmp_path: Path) -> None:
        """WhisperModel is instantiated with device='cpu' and compute_type='int8'."""
        wav = _make_silent_wav(tmp_path)
        mock_info = _make_mock_info("en")

        with patch("app.services.transcriber.WhisperModel") as MockModel:
            MockModel.return_value.transcribe.return_value = ([], mock_info)
            t = self._make_transcriber(model_size="small", compute_type="int8", device="cpu")
            t.transcribe(str(wav))

        MockModel.assert_called_once_with(
            "small",
            device="cpu",
            compute_type="int8",
            download_root=None,
        )

    def test_language_auto_passes_none_to_model(self, tmp_path: Path) -> None:
        """language='auto' passes language=None to model.transcribe() — lets the model detect."""
        wav = _make_silent_wav(tmp_path)
        mock_info = _make_mock_info("en")

        with patch("app.services.transcriber.WhisperModel") as MockModel:
            mock_instance = MockModel.return_value
            mock_instance.transcribe.return_value = ([], mock_info)
            t = self._make_transcriber(language="auto")
            t.transcribe(str(wav))

        call_kwargs = mock_instance.transcribe.call_args
        assert call_kwargs.kwargs.get("language") is None

    def test_model_lazy_loaded_on_first_transcribe(self, tmp_path: Path) -> None:
        """WhisperModel is NOT instantiated at __init__ time — only on first transcribe()."""
        wav = _make_silent_wav(tmp_path)
        mock_info = _make_mock_info("en")

        with patch("app.services.transcriber.WhisperModel") as MockModel:
            MockModel.return_value.transcribe.return_value = ([], mock_info)
            t = self._make_transcriber()
            MockModel.assert_not_called()
            t.transcribe(str(wav))
            MockModel.assert_called_once()

    def test_transcription_result_has_correct_types(self, tmp_path: Path) -> None:
        """TranscriptionResult fields have the expected Python types."""
        wav = _make_silent_wav(tmp_path)
        mock_words = [_make_mock_word("test", 0.0, 0.3)]
        mock_segment = _make_mock_segment("test", mock_words)
        mock_info = _make_mock_info("en")

        with patch("app.services.transcriber.WhisperModel") as MockModel:
            MockModel.return_value.transcribe.return_value = ([mock_segment], mock_info)
            result = self._make_transcriber().transcribe(str(wav))

        assert isinstance(result.text, str)
        assert isinstance(result.language, str)
        assert isinstance(result.words, list)
        assert isinstance(result.words[0], WordTimestamp)
        assert isinstance(result.words[0].w, str)
        assert isinstance(result.words[0].start, float)
        assert isinstance(result.words[0].end, float)

    def test_empty_segments_returns_empty_result(self, tmp_path: Path) -> None:
        """Silence or inaudible audio (no segments) returns empty text and empty word list."""
        wav = _make_silent_wav(tmp_path)
        mock_info = _make_mock_info("en")

        with patch("app.services.transcriber.WhisperModel") as MockModel:
            MockModel.return_value.transcribe.return_value = ([], mock_info)
            result = self._make_transcriber().transcribe(str(wav))

        assert result.text == ""
        assert result.words == []
