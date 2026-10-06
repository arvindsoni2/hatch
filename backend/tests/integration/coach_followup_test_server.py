"""Actual Coach app with deterministic, transcript-grounded model evaluation."""

from coach_browser_test_server import SyntheticModel, app as app

from app.services import llm_client
from app.services.coach_conversational_contracts import CONTENT_DIMENSIONS


def _transcript(prompt: str) -> str:
    return prompt.rsplit("<transcript>", 1)[1].split("</transcript>", 1)[0]


class SyntheticFollowUpModel(SyntheticModel):
    async def complete_json(self, system_prompt, user_prompt, *, max_tokens):
        if "evaluate interview answer content" in system_prompt:
            answer = _transcript(user_prompt)
            gap = (
                "impact"
                if "stakeholders were satisfied" in answer
                else "specificity" if "three hours" in answer else None
            )
            span = {
                "transcript_start": 0,
                "transcript_end": len(answer),
                "excerpt": answer,
            }
            return {
                "dimensions": {
                    name: {
                        "level": "developing" if name == gap else "interview_ready",
                        "evidence": [span],
                        "rationale": "The synthetic answer describes a delivery action.",
                        "improvement": "Add a concrete result." if name == gap else None,
                    }
                    for name in CONTENT_DIMENSIONS
                }
            }
        if "adaptive interview follow-up" in system_prompt:
            answer = _transcript(user_prompt)
            if "stakeholders were satisfied" in answer:
                reason, question, target, role, key = (
                    "measurable_result",
                    "What measurable outcome resulted from the migration?",
                    "impact",
                    "gap_repair",
                    "synthetic-root-impact-result",
                )
            elif "three hours" in answer:
                reason, question, target, role, key = (
                    "personal_action",
                    "What did you personally do to reduce deployment time?",
                    "specificity",
                    "gap_repair",
                    "synthetic-root-personal-action",
                )
            elif "personally automated" in answer:
                reason, question, target, role, key = (
                    "reasoning",
                    "Why did you choose to automate the deployment checks?",
                    "role_depth",
                    "primary_evidence",
                    "synthetic-root-reasoning-third",
                )
            else:
                return await super().complete_json(
                    system_prompt, user_prompt, max_tokens=max_tokens
                )
            return {
                "should_ask": True,
                "reason": reason,
                "question": question,
                "transcript_evidence": {
                    "start": 0,
                    "end": len(answer),
                    "excerpt": answer,
                },
                "target_dimension": target,
                "aggregation_role": role,
                "duplicate_key": key,
            }
        return await super().complete_json(
            system_prompt, user_prompt, max_tokens=max_tokens
        )


llm_client.LLMClient = SyntheticFollowUpModel
