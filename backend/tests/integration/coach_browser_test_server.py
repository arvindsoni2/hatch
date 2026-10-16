"""Real Coach app for browser tests, with model and ASR providers replaced."""

from pathlib import Path

from app.main import app as app
from app.agents.tools import perception_factory
from app.services import llm_client
from app.services.coach_conversational_contracts import CONTENT_DIMENSIONS
from app.services.transcriber import TranscriptionResult, WordTimestamp


SYNTHETIC_ANSWER = "I led the migration and reduced deployment time by three hours."


class SyntheticModel:
    async def complete_json(self, system_prompt, _user_prompt, *, max_tokens):
        del max_tokens
        if "evaluate interview answer content" in system_prompt:
            span = {
                "transcript_start": 0,
                "transcript_end": len(SYNTHETIC_ANSWER),
                "excerpt": SYNTHETIC_ANSWER,
            }
            return {
                "dimensions": {
                    name: {
                        "level": "interview_ready",
                        "evidence": [span],
                        "rationale": "The synthetic answer gives a concrete example.",
                        "improvement": "Add one more constraint.",
                    }
                    for name in CONTENT_DIMENSIONS
                }
            }
        if "Ground candidate claims" in system_prompt:
            return {"claims": []}
        if "adaptive interview follow-up" in system_prompt:
            return {
                "should_ask": False,
                "reason": None,
                "question": None,
                "transcript_evidence": None,
                "target_dimension": None,
                "aggregation_role": None,
                "duplicate_key": None,
            }
        raise AssertionError("Unexpected synthetic model stage")


class SyntheticTranscriber:
    def transcribe(self, audio_path: str) -> TranscriptionResult:
        if Path(audio_path).stat().st_size == 0:
            raise ValueError("Synthetic audio fixture is empty")
        return TranscriptionResult(
            SYNTHETIC_ANSWER,
            "en",
            [
                WordTimestamp(word, index * 0.2, (index + 1) * 0.2)
                for index, word in enumerate(SYNTHETIC_ANSWER.split())
            ],
        )


# The production worker imports these providers at execution time. Routes,
# dispatch, persistence, reconciliation, and finalizers remain unmodified.
llm_client.LLMClient = SyntheticModel
perception_factory.get_transcriber = SyntheticTranscriber
