"""Stable, privacy-safe telemetry attributes owned by Hatch."""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

WORKFLOW_NAME = "hatch.ai.workflow.name"
PROVIDER_TYPE = "hatch.ai.provider.type"
MODEL_ID = "hatch.ai.model.id"
PROMPT_ID = "hatch.ai.prompt.id"
PROMPT_VERSION = "hatch.ai.prompt.version"
SKILL_ID = "hatch.ai.skill.id"
SKILL_VERSION = "hatch.ai.skill.version"
ATTEMPT_NUMBER = "hatch.ai.attempt.number"
REPAIR_TYPE = "hatch.ai.repair.type"
VALIDATION_STATE = "hatch.ai.validation.state"
FAILED_GATE_CODES = "hatch.ai.validation.failed_gate_codes"
INPUT_TOKENS = "hatch.ai.tokens.input"
OUTPUT_TOKENS = "hatch.ai.tokens.output"
COVER_LETTER_BODY_COUNT = "hatch.ai.cover_letter.body_count"
BENCHMARK_RUN_ID = "hatch.ai.benchmark.run_id"
BENCHMARK_CASE_ID = "hatch.ai.benchmark.case_id"
BENCHMARK_SEED = "hatch.ai.benchmark.seed"
DOCUMENT_ID = "hatch.ai.document.id"

_STRING_KEYS = frozenset(
    {
        WORKFLOW_NAME,
        PROVIDER_TYPE,
        MODEL_ID,
        PROMPT_ID,
        PROMPT_VERSION,
        SKILL_ID,
        SKILL_VERSION,
        REPAIR_TYPE,
        VALIDATION_STATE,
        BENCHMARK_RUN_ID,
        BENCHMARK_CASE_ID,
        DOCUMENT_ID,
    }
)
_INTEGER_KEYS = frozenset(
    {
        ATTEMPT_NUMBER,
        INPUT_TOKENS,
        OUTPUT_TOKENS,
        COVER_LETTER_BODY_COUNT,
        BENCHMARK_SEED,
    }
)
_SEQUENCE_KEYS = frozenset({FAILED_GATE_CODES})
ALLOWED_ATTRIBUTE_KEYS = _STRING_KEYS | _INTEGER_KEYS | _SEQUENCE_KEYS
_SECRET_SHAPE = re.compile(
    r"(?i)(?:bearer\s+\S+|api[_-]?key|authorization|password|secret|token\s*[:=])"
)
_MAX_STRING_LENGTH = 128
_MAX_SEQUENCE_LENGTH = 32


def _safe_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized or _SECRET_SHAPE.search(normalized):
        return None
    return normalized[:_MAX_STRING_LENGTH]


def sanitize_attributes(
    attributes: Mapping[str, Any] | None,
) -> dict[str, str | int | tuple[str, ...]]:
    """Return only bounded, low-cardinality values from Hatch's allowlist."""
    sanitized: dict[str, str | int | tuple[str, ...]] = {}
    for key, value in (attributes or {}).items():
        if key in _STRING_KEYS:
            safe = _safe_string(value)
            if safe is not None:
                sanitized[key] = safe
        elif key in _INTEGER_KEYS and isinstance(value, int) and not isinstance(value, bool):
            if value >= 0:
                sanitized[key] = value
        elif key in _SEQUENCE_KEYS and isinstance(value, (list, tuple, set, frozenset)):
            safe_values = tuple(
                item
                for item in (_safe_string(candidate) for candidate in value)
                if item is not None
            )[:_MAX_SEQUENCE_LENGTH]
            if safe_values:
                sanitized[key] = safe_values
    return sanitized
