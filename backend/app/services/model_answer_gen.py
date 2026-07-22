"""Candidate-grounded Coach model answers with explicit safe outcomes."""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from ..agents.tools.context_budgets import MODEL_ANSWER
from ..config import settings
from ..observability import get_telemetry, trace_stage
from ..prompts import render_prompt
from ..schemas.coach import ModelAnswerResult
from .coach_contracts import (
    CoachDiagnostic,
    configured_attempt_count,
    configured_model_id,
    run_with_stage_deadline,
)
from .jd_analyser import _split_jinja_output
from .llm_client import LLMClient
from .prompt_catalog import (
    candidate_claim_contract,
    prompt_contract_block,
    prompt_metadata,
    validate_candidate_output,
)
from .writing_contracts import build_evidence_ledger, evidence_records

logger = logging.getLogger(__name__)

_STAR_KEYS = ("situation", "task", "action", "result")
_GROUNDING_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "because",
    "by",
    "for",
    "from",
    "had",
    "has",
    "have",
    "i",
    "in",
    "into",
    "it",
    "my",
    "of",
    "on",
    "our",
    "so",
    "that",
    "the",
    "their",
    "then",
    "this",
    "to",
    "was",
    "were",
    "we",
    "when",
    "while",
    "with",
    "through",
}


def _diagnostic(
    client: object,
    *,
    outcome: str,
    gates: list[str],
    duration_ms: int,
    execution_mode: str = "llm",
) -> CoachDiagnostic:
    if execution_mode != "llm":
        return CoachDiagnostic(
            stage="model_answer",
            outcome=outcome,
            execution_mode=execution_mode,
            attempt_count=0,
            repair_count=0,
            gate_codes=gates,
            duration_ms=duration_ms,
        )
    metadata = prompt_metadata("model_answer")
    return CoachDiagnostic(
        stage="model_answer",
        outcome=outcome,
        execution_mode="llm",
        prompt_id=metadata.prompt_id,
        prompt_version=metadata.prompt_version,
        output_schema_version=metadata.schema_version,
        model_id=configured_model_id(client),
        attempt_count=configured_attempt_count(client),
        repair_count=0,
        gate_codes=gates,
        duration_ms=duration_ms,
    )


def _empty_result(diagnostic: CoachDiagnostic) -> ModelAnswerResult:
    return ModelAnswerResult(
        model_answer="",
        star_breakdown={},
        evidence_references=[],
        diagnostic=diagnostic,
    )


class ModelAnswerGeneratorService:
    """Generate a STAR answer, withholding every unvalidated candidate claim."""

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
    ) -> ModelAnswerResult:
        ledger = build_evidence_ledger({"summary": candidate_summary})
        if not ledger:
            return _empty_result(
                _diagnostic(
                    self._client,
                    outcome="withheld_insufficient_evidence",
                    gates=["coach_model_answer_no_evidence"],
                    duration_ms=0,
                    execution_mode="not_run",
                )
            )

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
            raw = await run_with_stage_deadline(
                self._client.complete_json(
                    system_prompt,
                    user_prompt,
                    max_tokens=MODEL_ANSWER.max_output,
                ),
                settings.HATCH_COACH_TIMEOUT_MODEL_ANSWER_SECONDS,
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            get_telemetry().record_model_call(
                workflow="coach_generation",
                provider=type(self._client).__name__,
                model_id=configured_model_id(self._client),
                duration_ms=duration_ms,
                outcome="failed",
            )
            gate = (
                "coach_stage_timeout"
                if isinstance(exc, TimeoutError)
                else "coach_model_answer_provider_unavailable"
            )
            logger.warning("Model answer generation failed: %s", exc)
            return _empty_result(
                _diagnostic(
                    self._client,
                    outcome="unavailable",
                    gates=[gate],
                    duration_ms=duration_ms,
                )
            )

        duration_ms = int((time.monotonic() - started) * 1000)
        get_telemetry().record_model_call(
            workflow="coach_generation",
            provider=type(self._client).__name__,
            model_id=configured_model_id(self._client),
            duration_ms=duration_ms,
        )
        if not isinstance(raw, dict):
            return _empty_result(
                _diagnostic(
                    self._client,
                    outcome="invalid_output",
                    gates=["coach_model_answer_schema_invalid"],
                    duration_ms=duration_ms,
                )
            )

        model_answer = raw.get("model_answer")
        if not isinstance(model_answer, str) or not model_answer.strip():
            return _empty_result(
                _diagnostic(
                    self._client,
                    outcome="invalid_output",
                    gates=["coach_model_answer_empty"],
                    duration_ms=duration_ms,
                )
            )

        star = raw.get("star_breakdown")
        if not isinstance(star, dict) or any(
            not isinstance(star.get(key), str) or not star[key].strip()
            for key in _STAR_KEYS
        ):
            return _empty_result(
                _diagnostic(
                    self._client,
                    outcome="invalid_output",
                    gates=["coach_model_answer_star_incomplete"],
                    duration_ms=duration_ms,
                )
            )
        star_breakdown = {key: str(star[key]).strip() for key in _STAR_KEYS}

        references = raw.get("evidence_references", [])
        if not isinstance(references, list) or any(
            not isinstance(reference, str) for reference in references
        ):
            return _empty_result(
                _diagnostic(
                    self._client,
                    outcome="invalid_output",
                    gates=["coach_model_answer_schema_invalid"],
                    duration_ms=duration_ms,
                )
            )
        allowed_ids = {item.id for item in ledger}
        if any(reference not in allowed_ids for reference in references):
            return _empty_result(
                _diagnostic(
                    self._client,
                    outcome="invalid_output",
                    gates=["coach_model_answer_unknown_evidence_id"],
                    duration_ms=duration_ms,
                )
            )

        validation = validate_candidate_output(
            [model_answer, *star_breakdown.values()],
            ledger,
            _string_values(company_research or {}),
        )
        if not validation.passed:
            gate = (
                "coach_model_answer_numeric_fidelity"
                if any(issue.code == "unsupported_numeric_token" for issue in validation.issues)
                else "coach_model_answer_unsupported_claim"
            )
            get_telemetry().record_validation_failure("coach_generation", gate)
            return _empty_result(
                _diagnostic(
                    self._client,
                    outcome="invalid_output",
                    gates=[gate],
                    duration_ms=duration_ms,
                )
            )

        referenced_evidence = tuple(item for item in ledger if item.id in references)
        if not referenced_evidence or not all(
            _prose_is_grounded(prose, referenced_evidence)
            for prose in (model_answer, *star_breakdown.values())
        ):
            gate = "coach_model_answer_unsupported_claim"
            get_telemetry().record_validation_failure("coach_generation", gate)
            return _empty_result(
                _diagnostic(
                    self._client,
                    outcome="invalid_output",
                    gates=[gate],
                    duration_ms=duration_ms,
                )
            )

        return ModelAnswerResult(
            model_answer=model_answer.strip(),
            star_breakdown=star_breakdown,
            evidence_references=references,
            diagnostic=_diagnostic(
                self._client,
                outcome="completed",
                gates=[],
                duration_ms=duration_ms,
            ),
        )


def _string_values(value: Any) -> list[str]:
    """Flatten supplied employer context for numeric validation exemptions."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for nested in value.values() for text in _string_values(nested)]
    if isinstance(value, list):
        return [text for nested in value for text in _string_values(nested)]
    return []


def _content_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.casefold())
        if token not in _GROUNDING_STOPWORDS
    }


def _same_lexeme(left: str, right: str) -> bool:
    return left == right or (
        len(left) >= 5 and len(right) >= 5 and left[:5] == right[:5]
    )


def _prose_is_grounded(prose: str, evidence: tuple[Any, ...]) -> bool:
    """Conservatively require every material token in referenced evidence."""
    observed = _content_tokens(prose)
    supported = _content_tokens(" ".join(item.text for item in evidence))
    return bool(observed) and all(
        any(_same_lexeme(token, source) for source in supported)
        for token in observed
    )
