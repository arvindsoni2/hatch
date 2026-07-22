"""Model Answer Generator — produces STAR-structured model answers via Claude."""
from __future__ import annotations

import logging
import time
from typing import Any

from ..prompts import render_prompt
from ..observability import get_telemetry, trace_stage
from .llm_client import LLMClient
from ..agents.tools.context_budgets import MODEL_ANSWER
from .jd_analyser import _split_jinja_output
from .prompt_catalog import (
    candidate_claim_contract,
    prompt_contract_block,
    validate_candidate_output,
)
from .writing_contracts import build_evidence_ledger, evidence_records

logger = logging.getLogger(__name__)


class ModelAnswerGeneratorService:
    """Generates STAR-structured model answers for interview questions."""

    def __init__(self, claude_client: LLMClient) -> None:
        self._client = claude_client

    @trace_stage("coach_generation", "generate_initial")
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
        ledger = build_evidence_ledger({"summary": candidate_summary})
        if not ledger:
            return ""
        system_prompt, user_prompt = _split_jinja_output(
            render_prompt(
                "model_answer.j2",
                question=question,
                category=category,
                difficulty=difficulty,
                company_name=company_name,
                company_research=company_research or {},
                approved_evidence=evidence_records(ledger),
                prompt_contract=prompt_contract_block("model_answer"),
                candidate_contract=candidate_claim_contract("model_answer"),
            )
        )
        started = time.monotonic()
        try:
            raw = await self._client.complete_json(
                system_prompt,
                user_prompt,
                max_tokens=MODEL_ANSWER.max_output,
            )
            get_telemetry().record_model_call(
                workflow="coach_generation",
                provider=type(self._client).__name__,
                model_id=str(getattr(self._client, "model", "configured")),
                duration_ms=(time.monotonic() - started) * 1000,
            )
            if not isinstance(raw, dict):
                get_telemetry().record_validation_failure(
                    "coach_generation",
                    "invalid_model_answer",
                )
                return ""
            model_answer = raw.get("model_answer", "")
            if not isinstance(model_answer, str) or not model_answer.strip():
                get_telemetry().record_validation_failure(
                    "coach_generation",
                    "missing_model_answer",
                )
                return ""
            star = raw.get("star_breakdown", {})
            star_prose = (
                [str(value) for value in star.values()]
                if isinstance(star, dict)
                else []
            )
            employer_context = _string_values(company_research or {})
            validation = validate_candidate_output(
                [model_answer, *star_prose],
                ledger,
                employer_context,
            )
            if not validation.passed:
                get_telemetry().record_validation_failure(
                    "coach_generation",
                    "candidate_grounding",
                )
            return model_answer if validation.passed else ""
        except Exception as exc:
            get_telemetry().record_model_call(
                workflow="coach_generation",
                provider=type(self._client).__name__,
                model_id=str(getattr(self._client, "model", "configured")),
                duration_ms=(time.monotonic() - started) * 1000,
                outcome="failed",
            )
            get_telemetry().mark_current_error(
                "model_answer_failed",
                "model_error",
            )
            logger.warning("Model answer generation failed: %s", exc)
            return ""


def _string_values(value: Any) -> list[str]:
    """Flatten supplied employer context for numeric validation exemptions."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [
            text
            for nested in value.values()
            for text in _string_values(nested)
        ]
    if isinstance(value, list):
        return [text for nested in value for text in _string_values(nested)]
    return []
