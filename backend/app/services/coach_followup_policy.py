"""Deterministic admission policy for conversational adaptive follow-ups."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

from .coach_conversational_contracts import FOLLOW_UP_REASON_MAPPING
from .coach_text_spans import (
    ContractValidationError,
    scan_prohibited_model_authorship,
    validate_code_point_span,
)


_PROPOSAL_KEYS = frozenset(
    {
        "should_ask",
        "reason",
        "question",
        "transcript_evidence",
        "target_dimension",
        "aggregation_role",
        "duplicate_key",
    }
)
_SPAN_KEYS = frozenset({"start", "end", "excerpt"})
_PROHIBITED_SCORE_PATTERN = re.compile(
    r"(?:\bscore\b|\bconfidence\b|\b\d+(?:\.\d+)?\s*(?:/\s*10|%))",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FollowUpContext:
    transcript: str
    accepted_attempt_id: str
    current_accepted_attempt_id: str | None
    target_dimension_levels: Mapping[str, str]
    existing_duplicate_keys: tuple[str, ...]
    persisted_follow_up_count: int
    root_skipped: bool
    session_ended: bool


@dataclass(frozen=True)
class FollowUpDecision:
    admitted: bool
    error_code: str | None = None
    reason: str | None = None
    question: str | None = None
    target_dimension: str | None = None
    aggregation_role: str | None = None
    duplicate_key: str | None = None
    transcript_start: int | None = None
    transcript_end: int | None = None
    transcript_excerpt: str | None = None


class FollowUpPolicy:
    """Validate model proposals against current persisted admission authority."""

    def validate(
        self, proposal: object, context: FollowUpContext
    ) -> FollowUpDecision:
        if not isinstance(proposal, Mapping) or set(proposal) != _PROPOSAL_KEYS:
            return self._invalid()
        should_ask = proposal.get("should_ask")
        if should_ask is False:
            if any(proposal.get(key) is not None for key in _PROPOSAL_KEYS - {"should_ask"}):
                return self._invalid()
            return FollowUpDecision(admitted=False)
        if should_ask is not True:
            return self._invalid()

        reason = proposal.get("reason")
        question = proposal.get("question")
        target_dimension = proposal.get("target_dimension")
        aggregation_role = proposal.get("aggregation_role")
        duplicate_key_value = proposal.get("duplicate_key")
        evidence = proposal.get("transcript_evidence")
        if (
            not isinstance(reason, str)
            or not isinstance(question, str)
            or not isinstance(target_dimension, str)
            or not isinstance(aggregation_role, str)
            or not isinstance(duplicate_key_value, str)
            or not isinstance(evidence, Mapping)
            or set(evidence) != _SPAN_KEYS
            or FOLLOW_UP_REASON_MAPPING.get(reason)
            != (target_dimension, aggregation_role)
        ):
            return self._invalid()

        normalized_question = unicodedata.normalize("NFC", question).strip()
        duplicate_key = unicodedata.normalize(
            "NFKC", duplicate_key_value
        ).strip().casefold()
        if (
            not normalized_question
            or len(normalized_question) > 1_000
            or not duplicate_key
            or len(duplicate_key) > 256
            or scan_prohibited_model_authorship({"question": normalized_question})
            or _PROHIBITED_SCORE_PATTERN.search(normalized_question)
            or context.current_accepted_attempt_id != context.accepted_attempt_id
            or context.root_skipped
            or context.session_ended
            or context.persisted_follow_up_count >= 2
            or duplicate_key
            in {
                unicodedata.normalize("NFKC", key).strip().casefold()
                for key in context.existing_duplicate_keys
            }
        ):
            return self._invalid()
        if aggregation_role == "gap_repair" and context.target_dimension_levels.get(
            target_dimension
        ) not in {"needs_work", "developing"}:
            return self._invalid()

        try:
            span = validate_code_point_span(
                context.transcript,
                evidence.get("start"),
                evidence.get("end"),
                evidence.get("excerpt"),
            )
        except (ContractValidationError, TypeError):
            return self._invalid()
        return FollowUpDecision(
            admitted=True,
            reason=reason,
            question=normalized_question,
            target_dimension=target_dimension,
            aggregation_role=aggregation_role,
            duplicate_key=duplicate_key,
            transcript_start=span.start,
            transcript_end=span.end,
            transcript_excerpt=span.excerpt,
        )

    @staticmethod
    def _invalid() -> FollowUpDecision:
        return FollowUpDecision(
            admitted=False, error_code="coach_followup_reason_invalid"
        )
