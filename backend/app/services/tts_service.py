"""Piper TTS service — synthesise interview questions to WAV audio via the piper CLI.

Phase E of the Coach Module Uplift.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import struct
import wave
from io import BytesIO

from .._exceptions import PerceptionNotAvailableError

logger = logging.getLogger(__name__)


def _wrap_pcm_in_wav(pcm_bytes: bytes, sample_rate: int = 22050, channels: int = 1, sample_width: int = 2) -> bytes:
    """Wrap raw PCM bytes in a WAV container.

    Args:
        pcm_bytes: Raw PCM audio data.
        sample_rate: Sample rate in Hz (piper default is 22050).
        channels: Number of audio channels (1 = mono).
        sample_width: Bytes per sample (2 = 16-bit).

    Returns:
        Complete WAV file as bytes.
    """
    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


class PiperTTSService:
    """Wraps the piper CLI to generate WAV audio from text.

    Requires the `piper` binary to be available in PATH and the model file
    configured via profile.yaml → perception.tts.voice.

    Raises:
        PerceptionNotAvailableError: if the piper binary is not found.
    """

    def __init__(self, voice: str = "en_GB-alan-medium") -> None:
        self.voice = voice

    async def synthesise(self, text: str) -> bytes:
        """Return WAV bytes for the given text.

        Args:
            text: The text to convert to speech.

        Returns:
            WAV audio bytes.

        Raises:
            PerceptionNotAvailableError: if piper binary is not in PATH.
            RuntimeError: if piper exits with non-zero status.
        """
        if not shutil.which("piper"):
            raise PerceptionNotAvailableError(
                "piper binary not found in PATH. "
                "Install piper-tts: pip install piper-tts or see https://github.com/rhasspy/piper"
            )

        proc = await asyncio.create_subprocess_exec(
            "piper",
            "--model", self.voice,
            "--output-raw",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        try:
            stdout, _ = await asyncio.wait_for(
                proc.communicate(text.encode("utf-8")), timeout=30
            )
        except asyncio.TimeoutError as exc:
            proc.kill()
            raise RuntimeError("piper TTS timed out after 30 seconds") from exc

        if proc.returncode != 0:
            raise RuntimeError(f"piper exited with status {proc.returncode}")

        return _wrap_pcm_in_wav(stdout)
