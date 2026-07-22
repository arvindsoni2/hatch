"""Candidate-grounded Coach model answers with explicit safe outcomes."""
from __future__ import annotations

import logging
import re
import time
import unicodedata
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
_STAR_ROLE_PATTERNS = {
    "situation": re.compile(
        r"\b(?:was|were|had|faced|during|when|context|environment|project|service|team)\b",
        re.IGNORECASE,
    ),
    "task": re.compile(
        r"\b(?:needed|required|responsible|tasked|goal|objective|challenge|had to|aimed)\b",
        re.IGNORECASE,
    ),
    "action": re.compile(
        r"\b(?:i|we)\s+(?:(?:personally|then|also)\s+){0,2}"
        r"(?!(?:needed|required|tasked|aimed|achieved|grew|improved|increased|"
        r"decreased|reduced|saved|fell|resulted|delivered)\b)"
        r"(?:[a-z]{3,}ed|built|chose|drove|led|made|ran|took|wrote)\b",
        re.IGNORECASE,
    ),
    "result": re.compile(
        r"\b(?:achieved|grew|improved|increased|decreased|reduced|saved|fell|"
        r"resulted|outcome|delivered)\b",
        re.IGNORECASE,
    ),
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
        ledger = _build_candidate_evidence(candidate_summary)
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
        if _is_explicit_withholding(raw):
            return _empty_result(
                _diagnostic(
                    self._client,
                    outcome="withheld_insufficient_evidence",
                    gates=["coach_model_answer_no_evidence"],
                    duration_ms=duration_ms,
                )
            )
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
        if len({_normalized_claim(value) for value in star_breakdown.values()}) != len(
            _STAR_KEYS
        ):
            return _empty_result(
                _diagnostic(
                    self._client,
                    outcome="invalid_output",
                    gates=["coach_model_answer_star_incomplete"],
                    duration_ms=duration_ms,
                )
            )

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

        if any(_star_roles(value) != {key} for key, value in star_breakdown.items()):
            return _empty_result(
                _diagnostic(
                    self._client,
                    outcome="invalid_output",
                    gates=["coach_model_answer_star_incomplete"],
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


def _is_explicit_withholding(raw: dict[str, Any]) -> bool:
    star = raw.get("star_breakdown")
    return (
        isinstance(raw.get("model_answer"), str)
        and not raw["model_answer"].strip()
        and isinstance(star, dict)
        and all(
            isinstance(star.get(key), str) and not star[key].strip()
            for key in _STAR_KEYS
        )
        and raw.get("evidence_references") == []
    )


def _content_tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    tokens: list[str] = []
    current: list[str] = []
    for character in normalized:
        if character.isalnum():
            current.append(character)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens


def _normalized_claim(text: str) -> tuple[str, ...]:
    return tuple(_content_tokens(text))


def _star_roles(text: str) -> set[str]:
    return {
        role for role, pattern in _STAR_ROLE_PATTERNS.items() if pattern.search(text)
    }


def _tokens_match_claim(observed: list[str], supported: list[str]) -> bool:
    """Require exact normalized clause tokens; semantic paraphrase is withheld."""
    return observed == supported


def _prose_is_grounded(prose: str, evidence: tuple[Any, ...]) -> bool:
    """Require each generated clause to match one atomic evidence record."""
    claims = [
        claim.strip(" \t-*•")
        for claim in re.split(r"[.!?]+|\n+|\s+[–—]\s+|\s*;\s*", prose)
        if claim.strip(" \t-*•")
    ]
    evidence_tokens = [_content_tokens(item.text) for item in evidence]
    return bool(claims) and all(
        bool(observed := _content_tokens(claim))
        and any(
            _tokens_match_claim(observed, supported)
            for supported in evidence_tokens
        )
        for claim in claims
    )


def _build_candidate_evidence(candidate_summary: str) -> tuple[Any, ...]:
    """Split combined prompt context into atomic candidate evidence records."""
    segments = [
        re.sub(r"^(?:summary|key skills):\s*", "", segment.strip(), flags=re.IGNORECASE)
        for segment in re.split(r"(?<=[.!?])\s+|\n+|\s*;\s*", candidate_summary)
        if segment.strip()
    ]
    return build_evidence_ledger(
        {"summary_variants": {f"claim_{index}": value for index, value in enumerate(segments)}}
    )
