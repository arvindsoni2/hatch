"""Stable Coach stage outcomes, diagnostics, and deadline helpers.

The types in this module are shared by production persistence and later
benchmark adapters.  They intentionally contain metadata only: prompt and
response content, candidate data, transcripts, URLs, and paths do not belong
in a :class:`CoachDiagnostic`.
"""
from __future__ import annotations

import asyncio
import copy
import re
from collections.abc import Awaitable
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import Self

COACH_VALIDATION_SCHEMA_VERSION = "1.0.0"

_CANDIDATE_HISTORY_VERBS = (
    r"built|created|delivered|designed|implemented|led|managed|reduced|saved|"
    r"worked|achieved|increased|decreased|drove|owned|launched|migrated|"
    r"developed|engineered|deployed|ran|oversaw|authored|coordinated|"
    r"orchestrated|facilitated|supported|contributed|directed|transformed|"
    r"improved|resolved|negotiated|mentored|advised|established|introduced|"
    r"optimized|optimised|streamlined|scaled|modernized|modernised"
    r"|owns|leads|wrote|written|chose|chosen|spearheaded|pioneered|set|cut"
)
_CANDIDATE_HISTORY_CLAIM = re.compile(
    rf"\b(?:i|we|you|he|she|they|the candidate|candidate)\b"
    rf"(?:\s+\w+){{0,4}}\s+"
    rf"(?:{_CANDIDATE_HISTORY_VERBS})\b|"
    rf"\b(?:was|were)\s+(?:{_CANDIDATE_HISTORY_VERBS})\s+by\s+"
    rf"(?:me|us|you|him|her|them|the candidate|[A-Za-z]{{2,30}})\b",
    re.IGNORECASE,
)
_NAMED_CANDIDATE_HISTORY_CLAIM = re.compile(
    rf"\b[A-Z][a-z]{{1,30}}(?:\s+[A-Z][a-z]{{1,30}})?"
    rf"(?:\s+(?:has|had))?(?:\s+\w+ly)?\s+"
    rf"(?:{_CANDIDATE_HISTORY_VERBS})\b"
)
_GENERIC_PAST_CANDIDATE_CLAIM = re.compile(
    r"\b(?:i|we|you|he|she|they|the candidate|candidate)\b"
    r"(?:\s+\w+){0,4}\s+(?!(?:need|seed|feed|speed)\b)[a-z]{3,}ed\b",
    re.IGNORECASE,
)
_EMBEDDED_NAMED_PAST_CLAIM = re.compile(
    r"\b[a-z]+\s+"
    r"[A-Z][a-z]{1,30}(?:\s+[A-Z][a-z]{1,30})?"
    r"(?:\s+(?:has|had))?(?:\s+\w+ly)?\s+"
    r"(?:(?!(?:need|seed|feed|speed)\b)[a-z]{3,}ed|wrote|made|took|gave|"
    r"came|saw|found|thought|told|became|showed|left|felt|put|brought|began|"
    r"kept|held|stood|heard|meant|met|set|learnt|grew|won|lost|paid|sent|"
    r"sat|spoke|lay|ran|drove|led|built|chose)\b(?!\s+its\b)"
)
_NAMED_RESPONSIBILITY_CLAIM = re.compile(
    r"\b(?:[A-Z][a-z]{1,30}(?:\s+[A-Z][a-z]{1,30})?|[Tt]he candidate|[Cc]andidate)\s+"
    r"(?:was|is|became)\s+responsible\s+for\b"
)


class CoachConflictError(RuntimeError):
    """A Coach database state rejected a requested transition."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class StaleWorkerFencedError(RuntimeError):
    """A reconciled or superseded worker attempted a terminal write."""


def failed_answer_payload(
    *,
    gate_code: str = "coach_async_job_failed",
    reason_code: str | None = None,
    retryable: bool = True,
) -> dict[str, object]:
    """Build the persisted no-score payload for an operationally failed attempt."""
    diagnostic: dict[str, object] = {
        "validation_schema_version": COACH_VALIDATION_SCHEMA_VERSION,
        "stage": "answer_evaluation",
        "outcome": "failed",
        "execution_mode": "deterministic",
        "prompt_id": None,
        "prompt_version": None,
        "output_schema_version": None,
        "model_id": None,
        "attempt_count": 0,
        "repair_count": 0,
        "gate_codes": [gate_code],
        "duration_ms": 0,
    }
    payload: dict[str, object] = {
        "evaluation_state": "failed",
        "diagnostic": diagnostic,
        "scores": {},
        "overall": None,
        "feedback": "Evaluation could not be completed. Please try again.",
        "strengths": [],
        "improvements": [],
        "evidence_references": [],
        "follow_up_question": None,
        "speech_coaching": [],
        "rubric": None,
        "retryable": retryable,
    }
    if reason_code:
        payload["reason_code"] = reason_code
    return payload

CoachStage = Literal[
    "company_research",
    "question_generation",
    "question_generation_repair",
    "model_answer",
    "answer_evaluation",
    "rubric_build",
    "rubric_synthesis",
    "technical_drill",
    "session_report",
    "session_rubric_aggregation",
    "followup_plan",
]
CoachOutcome = Literal[
    "completed",
    "withheld_insufficient_evidence",
    "fallback_deterministic",
    "invalid_output",
    "unavailable",
    "failed",
]
CoachExecutionMode = Literal["llm", "deterministic", "cache", "not_run"]
EvaluationState = Literal[
    "pending", "completed", "unavailable", "invalid", "skipped", "failed"
]
ReportState = Literal["not_started", "building", "completed", "fallback", "failed"]

CoachGateCode = Literal[
    "coach_question_parse_invalid",
    "coach_question_count_mismatch",
    "coach_question_duplicate",
    "coach_question_category_invalid",
    "coach_question_difficulty_invalid",
    "coach_question_requirement_unknown",
    "coach_question_candidate_claim",
    "coach_question_prompt_injection_followed",
    "coach_question_repair_exhausted",
    "coach_model_answer_no_evidence",
    "coach_model_answer_empty",
    "coach_model_answer_schema_invalid",
    "coach_model_answer_unknown_evidence_id",
    "coach_model_answer_unsupported_claim",
    "coach_model_answer_numeric_fidelity",
    "coach_model_answer_star_incomplete",
    "coach_model_answer_provider_unavailable",
    "coach_answer_empty_transcript",
    "coach_evaluation_schema_invalid",
    "coach_evaluation_dimension_missing",
    "coach_evaluation_score_out_of_range",
    "coach_evaluation_overall_inconsistent",
    "coach_evaluation_evidence_ungrounded",
    "coach_evaluation_followup_missing",
    "coach_evaluation_followup_unexpected",
    "coach_evaluation_provider_unavailable",
    "coach_evaluation_fallback_unclassified",
    "coach_rubric_dimension_missing",
    "coach_rubric_score_mutation",
    "coach_rubric_evidence_ungrounded",
    "coach_rubric_optional_dimension_unexpected",
    "coach_rubric_provider_unavailable",
    "coach_report_count_mismatch",
    "coach_report_score_mutation",
    "coach_report_unsupported_claim",
    "coach_report_priority_mismatch",
    "coach_report_schema_invalid",
    "coach_report_provider_unavailable",
    "coach_report_fallback_unclassified",
    "coach_drill_schema_invalid",
    "coach_drill_question_mismatch",
    "coach_drill_candidate_claim",
    "coach_drill_length_exceeded",
    "coach_drill_provider_unavailable",
    "coach_stage_timeout",
    "coach_job_timeout",
    "coach_stage_failed",
    "coach_async_job_failed",
    "coach_persistence_failed",
]


class CoachDiagnostic(BaseModel):
    """Privacy-safe metadata describing one terminal Coach stage attempt."""

    model_config = ConfigDict(extra="forbid")

    validation_schema_version: Literal["1.0.0"] = COACH_VALIDATION_SCHEMA_VERSION
    stage: CoachStage
    outcome: CoachOutcome
    execution_mode: CoachExecutionMode
    prompt_id: str | None = None
    prompt_version: str | None = None
    output_schema_version: str | None = None
    model_id: str | None = None
    attempt_count: int = Field(ge=0)
    repair_count: int = Field(ge=0)
    gate_codes: list[CoachGateCode]
    duration_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_execution_metadata(self) -> Self:
        prompt_metadata = (
            self.prompt_id,
            self.prompt_version,
            self.output_schema_version,
            self.model_id,
        )
        if self.execution_mode == "llm":
            if (
                not self.prompt_id
                or not self.prompt_version
                or not self.model_id
                or self.attempt_count < 1
            ):
                raise ValueError(
                    "LLM diagnostics require prompt/model metadata and at least one attempt"
                )
        elif any(value is not None for value in prompt_metadata):
            raise ValueError("non-LLM diagnostics cannot contain prompt/model metadata")
        return self


def merge_stage_diagnostic(
    existing: dict[str, Any] | None,
    stage: CoachStage | str,
    value: dict[str, Any],
) -> dict[str, Any]:
    """Return a copy with one stage replaced without dropping other stages."""
    merged: dict[str, Any] = copy.deepcopy(existing or {})
    merged["schema_version"] = COACH_VALIDATION_SCHEMA_VERSION
    stages = merged.get("stages")
    if not isinstance(stages, dict):
        stages = {}
        merged["stages"] = stages
    stages[str(stage)] = copy.deepcopy(value)
    return merged


_T = TypeVar("_T")


async def run_with_stage_deadline(
    awaitable: Awaitable[_T],
    seconds: float,
) -> _T:
    """Run one logical stage under a single non-renewable outer deadline."""
    async with asyncio.timeout(seconds):
        return await awaitable


def configured_model_id(client: object) -> str:
    """Return the configured model identifier without inspecting model output."""
    return str(getattr(client, "model", None) or "configured")


def configured_attempt_count(client: object) -> int:
    """Return a task-local provider-attempt count when the client exposes one."""
    value = getattr(client, "last_json_attempt_count", 1)
    return value if isinstance(value, int) and value >= 1 else 1


def contains_candidate_history_claim(
    text: str,
    *,
    allowed_entity_names: tuple[str, ...] = (),
    candidate_names: tuple[str, ...] = (),
) -> bool:
    """Detect unsupported candidate-history assertions in narrative output."""
    candidate_text = text
    for entity_name in allowed_entity_names:
        if entity_name.strip():
            candidate_text = re.sub(
                rf"\b{re.escape(entity_name.strip())}\b",
                "the employer",
                candidate_text,
                flags=re.IGNORECASE,
            )
    if any(
        pattern.search(candidate_text)
        for pattern in (
            _CANDIDATE_HISTORY_CLAIM,
            _GENERIC_PAST_CANDIDATE_CLAIM,
            _EMBEDDED_NAMED_PAST_CLAIM,
            _NAMED_RESPONSIBILITY_CLAIM,
        )
    ):
        return True
    return any(
        re.search(
            rf"\b{re.escape(candidate_name.strip())}\b"
            rf"\s+(?:(?:is|was|are|were)\s+"
            rf"(?:(?!(?:should|shall|can|could|may|might|must|would|will)\b)[a-z]+\s+)?"
            rf"[a-z]{{3,}}ing|(?:has|had)\s+"
            rf"(?:(?!(?:should|shall|can|could|may|might|must|would|will)\b)[a-z]+\s+)?(?:"
            rf"been\s+(?:(?!(?:should|shall|can|could|may|might|must|would|will)\b)"
            rf"[a-z]+\s+)?[a-z]{{3,}}ing|"
            rf"(?:{_CANDIDATE_HISTORY_VERBS}|[a-z]{{3,}}ed|set|cut))|"
            rf"(?:(?!(?:should|shall|can|could|may|might|must|would|will)\b)[a-z]+\s+)?"
            rf"(?:{_CANDIDATE_HISTORY_VERBS}|"
            rf"[a-z]{{3,}}ed|[a-z]{{3,}}s|set|cut))\b",
            candidate_text,
            flags=re.IGNORECASE,
        )
        for candidate_name in candidate_names
        if candidate_name.strip() and candidate_name.casefold() != "candidate"
    )


def candidate_name_aliases(full_name: str) -> tuple[str, ...]:
    """Return the full and given name used to identify candidate assertions."""
    normalized = " ".join(full_name.split())
    if not normalized or normalized.casefold() == "candidate":
        return ()
    first_name = normalized.split()[0]
    return tuple(dict.fromkeys((normalized, first_name)))
