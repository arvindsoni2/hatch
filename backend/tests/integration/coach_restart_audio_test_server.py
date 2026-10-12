"""Real Coach app with a bounded, synthetic ASR gate for process-crash tests."""

import os
import time
from pathlib import Path

from coach_browser_test_server import SyntheticModel, SyntheticTranscriber, app as app

from app.agents.tools import perception_factory
from app.services import llm_client


class GatedTranscriber(SyntheticTranscriber):
    def transcribe(self, audio_path: str):
        gate_root = Path(os.environ["HATCH_COACH_MEDIA_ROOT"]).parent
        (gate_root / "restart-transcription-entered").touch()
        deadline = time.monotonic() + 30
        while not (gate_root / "allow-restart-transcription").exists():
            if time.monotonic() >= deadline:
                raise TimeoutError("Synthetic ASR gate was not released")
            time.sleep(0.05)
        return super().transcribe(audio_path)


llm_client.LLMClient = SyntheticModel
perception_factory.get_transcriber = GatedTranscriber
