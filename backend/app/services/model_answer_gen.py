"""Model Answer Generator — produces STAR-structured model answers via Claude."""
from __future__ import annotations

import logging
from typing import Any

from ..prompts import render_prompt
from .llm_client import LLMClient
from ..agents.tools.context_budgets import MODEL_ANSWER
from .jd_analyser import _split_jinja_output

logger = logging.getLogger(__name__)


class ModelAnswerGeneratorService:
    """Generates STAR-structured model answers for interview questions."""

    def __init__(self, claude_client: LLMClient) -> None:
        self._client = claude_client

    async def generate(
        self,
        question: str,
        category: str,
        difficulty: str,
        company_name: str,
        company_research: dict[str, Any] | None = None,
        candidate_summary: str = "",
    ) -> str:
        """Generate a STAR-structured model answer for a single question.

        Args:
            question: The interview question text.
            category: Question category (Technical, Behavioural, etc.).
            difficulty: Question difficulty level.
            company_name: Company name for context.
            company_research: Optional company research dict.
            candidate_summary: Candidate CV summary text.

        Returns:
            Model answer as a plain text string.
        """
        system_prompt, user_prompt = _split_jinja_output(
            render_prompt(
                "model_answer.j2",
                question=question,
                category=category,
                difficulty=difficulty,
                company_name=company_name,
                company_research=company_research or {},
                candidate_summary=candidate_summary or "Senior Solutions Architect with 20+ years experience.",
            )
        )
        try:
            raw = await self._client.complete_json(system_prompt, user_prompt, max_tokens=MODEL_ANSWER.max_output)
            return raw.get("model_answer", "")
        except Exception as exc:
            logger.warning("Model answer generation failed: %s", exc)
            return ""
