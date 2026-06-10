"""Tests for PiperTTSService and get_tts() — Phase E."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app._exceptions import PerceptionNotAvailableError
from app.services.tts_service import PiperTTSService


# ---------------------------------------------------------------------------
# test_piper_raises_when_not_installed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_piper_raises_when_not_installed() -> None:
    """synthesise() raises PerceptionNotAvailableError when piper binary is absent."""
    with patch("app.services.tts_service.shutil.which", return_value=None):
        svc = PiperTTSService(voice="en_GB-alan-medium")
        with pytest.raises(PerceptionNotAvailableError, match="piper binary not found"):
            await svc.synthesise("Hello, this is a test.")


# ---------------------------------------------------------------------------
# test_get_tts_raises_when_provider_none
# ---------------------------------------------------------------------------

def test_get_tts_raises_when_provider_none() -> None:
    """get_tts() raises PerceptionNotAvailableError when provider is 'none'."""
    mock_profile = MagicMock()
    mock_profile.perception.tts.provider = "none"

    with patch("app.agents.tools.perception_factory.load_profile", return_value=mock_profile):
        from app.agents.tools.perception_factory import get_tts
        with pytest.raises(PerceptionNotAvailableError, match="TTS is disabled"):
            get_tts()


def test_get_tts_returns_piper_service_when_provider_piper() -> None:
    """get_tts() returns PiperTTSService when provider is 'piper'."""
    mock_profile = MagicMock()
    mock_profile.perception.tts.provider = "piper"
    mock_profile.perception.tts.voice = "en_GB-alan-medium"

    with patch("app.agents.tools.perception_factory.load_profile", return_value=mock_profile):
        from app.agents.tools.perception_factory import get_tts
        svc = get_tts()
        assert isinstance(svc, PiperTTSService)
        assert svc.voice == "en_GB-alan-medium"


@pytest.mark.asyncio
async def test_piper_wraps_output_in_wav() -> None:
    """When piper is found and runs successfully, synthesise() returns WAV bytes."""
    # Build a mock subprocess with a proper async communicate method
    class _MockProc:
        returncode = 0

        async def communicate(self, data: bytes) -> tuple[bytes, bytes]:  # noqa: ANN001
            return (b"\x00\x01" * 100, b"")

    mock_proc = _MockProc()

    with patch("app.services.tts_service.shutil.which", return_value="/usr/bin/piper"), \
         patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        svc = PiperTTSService(voice="en_GB-alan-medium")
        wav_bytes = await svc.synthesise("Test question text")

    # WAV files start with 'RIFF'
    assert wav_bytes[:4] == b"RIFF"
