"""Real Coach app with synthetic audio and a gated edit-evaluation provider."""

import asyncio
import os
from pathlib import Path

from coach_browser_test_server import SyntheticModel, app as app

from app.agents.tools import perception_factory
from app.services import llm_client
from app.services.coach_conversational_contracts import CONTENT_DIMENSIONS
from app.services.transcriber import TranscriptionResult, WordTimestamp


ORIGINAL = (
    "In the synthetic migration I coordinated the release across two teams. "
    "I mapped dependencies, assigned owners, and wrote a reversible deployment "
    "checklist. When a test failed, I paused the rollout, isolated the failing "
    "service, and reran checks. The team then shipped safely and reduced "
    "deployment time by three hours."
)
EDITED = "I coordinated the migration and resolved the release issue."


class LongSyntheticTranscriber:
    def transcribe(self, audio_path: str) -> TranscriptionResult:
        if Path(audio_path).stat().st_size == 0:
            raise ValueError("Synthetic audio fixture is empty")
        return TranscriptionResult(
            ORIGINAL,
            "en",
            [
                WordTimestamp(word, index * 0.55, (index + 1) * 0.55)
                for index, word in enumerate(ORIGINAL.split())
            ],
        )


class GatedEditModel(SyntheticModel):
    async def complete_json(self, system_prompt, user_prompt, *, max_tokens):
        if "evaluate interview answer content" in system_prompt:
            answer = user_prompt.rsplit("<transcript>", 1)[1].split("</transcript>", 1)[0]
            if answer == EDITED:
                gate_root = Path(os.environ["HATCH_COACH_MEDIA_ROOT"]).parent
                (gate_root / "edit-evaluation-entered").touch()
                async with asyncio.timeout(20):
                    while not (gate_root / "release-edit-evaluation").exists():
                        await asyncio.sleep(0.05)
            span = {
                "transcript_start": 0,
                "transcript_end": len(answer),
                "excerpt": answer,
            }
            return {
                "dimensions": {
                    name: {
                        "level": "interview_ready",
                        "evidence": [span],
                        "rationale": "The synthetic answer names an action.",
                        "improvement": None,
                    }
                    for name in CONTENT_DIMENSIONS
                }
            }
        return await super().complete_json(
            system_prompt, user_prompt, max_tokens=max_tokens
        )


llm_client.LLMClient = GatedEditModel
perception_factory.get_transcriber = LongSyntheticTranscriber
