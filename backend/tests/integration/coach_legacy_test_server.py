"""Actual Coach app with only the legacy LLM provider boundary unavailable."""

from app.main import app as app
from app.services import coach_service, rubric_synthesiser


class UnavailableLegacyModel:
    last_json_attempt_count = 1

    async def complete_json(self, system_prompt, _user_prompt, **_kwargs):
        if "expert technical interviewer evaluating a candidate's answer" in system_prompt:
            return {
                "scores": {
                    "relevance": 7,
                    "star_structure": 7,
                    "technical_depth": 7,
                    "conciseness": 7,
                    "communication": 7,
                    "impact_metrics": 7,
                },
                "overall": 7.0,
                "feedback": "A synthetic, clearly described delivery example.",
                "evidence_references": ["I coordinated a synthetic migration"],
                "follow_up_question": None,
            }
        raise RuntimeError("synthetic legacy model unavailable")

    async def complete(self, *_args, **_kwargs):
        raise RuntimeError("synthetic legacy model unavailable")


coach_service.LLMClient = UnavailableLegacyModel


def _unavailable_rubric_model():
    raise RuntimeError("synthetic rubric model unavailable")


rubric_synthesiser.get_json_model = _unavailable_rubric_model
