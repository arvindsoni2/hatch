"""Real Coach app with ASR success and evaluator-only synthetic failure."""

from coach_browser_test_server import SyntheticModel, app as app

from app.services import llm_client


class UnavailableEvaluationModel(SyntheticModel):
    async def complete_json(self, system_prompt, user_prompt, *, max_tokens):
        if "evaluate interview answer content" in system_prompt:
            raise RuntimeError("synthetic evaluator unavailable")
        return await super().complete_json(
            system_prompt, user_prompt, max_tokens=max_tokens
        )


llm_client.LLMClient = UnavailableEvaluationModel
