"""Canonical text and model-authorship validation for conversational Coach."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


class ContractValidationError(ValueError):
    """A frontend-safe conversational contract validation failure."""


@dataclass(frozen=True)
class ValidatedSpan:
    start: int
    end: int
    excerpt: str


_QUOTED_CONTENT_FIELDS = frozenset(
    {
        "excerpt",
        "transcript_excerpt",
        "evidence_excerpt",
        "claim_text",
        "snapshot_text",
        "transcript",
    }
)
_PROHIBITED_AUTHORSHIP_TERMS = (
    "anxious",
    "deceptive",
    "culture fit",
    "vocal confidence",
    "personality",
    "emotion",
    "stress",
    "honesty",
    "deception",
    "presence",
    "eye contact",
    "facial expression",
    "head stability",
    "gesture frequency",
)
_PROHIBITED_PATTERNS = tuple(
    (term, re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE))
    for term in _PROHIBITED_AUTHORSHIP_TERMS
)


def normalize_contract_text(text: str) -> str:
    """Return the sole NFC/LF representation used by persisted text offsets."""

    return unicodedata.normalize(
        "NFC", str(text).replace("\r\n", "\n").replace("\r", "\n")
    )


def validate_code_point_span(
    text: str, start: int, end: int, excerpt: str
) -> ValidatedSpan:
    """Validate a zero-based Unicode code-point half-open text span."""

    normalized = normalize_contract_text(text)
    quoted = normalize_contract_text(excerpt)
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int)
        or not isinstance(end, int)
        or not 0 <= start < end <= len(normalized)
        or normalized[start:end] != quoted
    ):
        raise ContractValidationError("coach_evaluation_evidence_span_invalid")
    return ValidatedSpan(start=start, end=end, excerpt=quoted)


def _model_authored_strings(value: object, *, quoted: bool = False) -> list[str]:
    if quoted:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        strings: list[str] = []
        for key, child in value.items():
            strings.extend(
                _model_authored_strings(
                    child,
                    quoted=isinstance(key, str) and key in _QUOTED_CONTENT_FIELDS,
                )
            )
        return strings
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        strings = []
        for child in value:
            strings.extend(_model_authored_strings(child))
        return strings
    return []


def scan_prohibited_model_authorship(value: object) -> tuple[str, ...]:
    """Return prohibited judgements found only in model-authored fields."""

    authored_text = "\n".join(_model_authored_strings(value))
    return tuple(
        term for term, pattern in _PROHIBITED_PATTERNS if pattern.search(authored_text)
    )
