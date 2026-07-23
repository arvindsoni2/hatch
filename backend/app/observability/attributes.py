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

# Coach trace attributes. Correlation identifiers are deliberately excluded
# from metric labels by ``sanitize_metric_attributes`` below.
COACH_OPERATION = "hatch.coach.operation"
COACH_STAGE = "hatch.coach.stage"
COACH_OUTCOME = "hatch.coach.outcome"
COACH_GATE_CODE = "hatch.coach.gate_code"
COACH_RECORDING_MODE = "hatch.coach.recording_mode"
COACH_QUESTION_COUNT_REQUESTED = "hatch.coach.question_count_requested"
COACH_QUESTION_COUNT_GENERATED = "hatch.coach.question_count_generated"
COACH_QUESTION_INDEX = "hatch.coach.question_index"
COACH_QUESTION_CATEGORY = "hatch.coach.question_category"
COACH_HAS_JOB_DESCRIPTION = "hatch.coach.has_job_description"
COACH_HAS_COMPANY_RESEARCH = "hatch.coach.has_company_research"
COACH_RESEARCH_VERIFICATION_STATE = "hatch.coach.research_verification_state"
COACH_MODEL_ANSWER_OUTCOME = "hatch.coach.model_answer_outcome"
COACH_EVALUATION_STATE = "hatch.coach.evaluation_state"
COACH_RUBRIC_SOURCE = "hatch.coach.rubric_source"
COACH_REPORT_STATE = "hatch.coach.report_state"
COACH_QUESTION_COUNT_TOTAL = "hatch.coach.question_count_total"
COACH_QUESTION_COUNT_EVALUATED = "hatch.coach.question_count_evaluated"
COACH_QUESTION_COUNT_SKIPPED = "hatch.coach.question_count_skipped"
COACH_QUESTION_COUNT_UNAVAILABLE = "hatch.coach.question_count_unavailable"
COACH_QUESTION_COUNT_UNANSWERED = "hatch.coach.question_count_unanswered"
COACH_FOLLOWUP_FOCUS_COUNT = "hatch.coach.followup_focus_count"
COACH_SESSION_ID = "hatch.coach.session_id"
ASYNC_JOB_ID = "hatch.async_job_id"

# Benchmark correlation reuses PR42's authoritative shared keys where they
# already exist rather than introducing aliases.
COACH_BENCHMARK_RUN_ID = BENCHMARK_RUN_ID
COACH_SCENARIO_ID = BENCHMARK_CASE_ID
COACH_SUITE_VERSION = "hatch.coach.benchmark.suite_version"
COACH_REPETITION = "hatch.coach.benchmark.repetition"
COACH_PROFILE = "hatch.coach.benchmark.profile"
COACH_BENCHMARK_STATUS = "hatch.coach.benchmark.status"

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
        COACH_OPERATION,
        COACH_STAGE,
        COACH_OUTCOME,
        COACH_GATE_CODE,
        COACH_RECORDING_MODE,
        COACH_QUESTION_CATEGORY,
        COACH_RESEARCH_VERIFICATION_STATE,
        COACH_MODEL_ANSWER_OUTCOME,
        COACH_EVALUATION_STATE,
        COACH_RUBRIC_SOURCE,
        COACH_REPORT_STATE,
        COACH_SESSION_ID,
        ASYNC_JOB_ID,
        COACH_SUITE_VERSION,
        COACH_PROFILE,
        COACH_BENCHMARK_STATUS,
    }
)
_INTEGER_KEYS = frozenset(
    {
        ATTEMPT_NUMBER,
        INPUT_TOKENS,
        OUTPUT_TOKENS,
        COVER_LETTER_BODY_COUNT,
        BENCHMARK_SEED,
        COACH_QUESTION_COUNT_REQUESTED,
        COACH_QUESTION_COUNT_GENERATED,
        COACH_QUESTION_INDEX,
        COACH_QUESTION_COUNT_TOTAL,
        COACH_QUESTION_COUNT_EVALUATED,
        COACH_QUESTION_COUNT_SKIPPED,
        COACH_QUESTION_COUNT_UNAVAILABLE,
        COACH_QUESTION_COUNT_UNANSWERED,
        COACH_FOLLOWUP_FOCUS_COUNT,
        COACH_REPETITION,
    }
)
_BOOLEAN_KEYS = frozenset(
    {
        COACH_HAS_JOB_DESCRIPTION,
        COACH_HAS_COMPANY_RESEARCH,
    }
)
_SEQUENCE_KEYS = frozenset({FAILED_GATE_CODES})
ALLOWED_ATTRIBUTE_KEYS = _STRING_KEYS | _INTEGER_KEYS | _BOOLEAN_KEYS | _SEQUENCE_KEYS

_CORRELATION_KEYS = frozenset(
    {
        BENCHMARK_RUN_ID,
        BENCHMARK_CASE_ID,
        DOCUMENT_ID,
        COACH_SESSION_ID,
        ASYNC_JOB_ID,
    }
)
_SECRET_SHAPE = re.compile(
    r"(?i)(?:bearer\s+\S+|api[_-]?key|authorization|password|secret|token\s*[:=])"
)
_PATH_SHAPE = re.compile(
    r"(?i)(?:^[/\\\\]|^[a-z]:[\\\\/]|^~[/\\\\]|^file://|/(?:home|users|tmp|var)/)"
)
_MAX_STRING_LENGTH = 128
_MAX_SEQUENCE_LENGTH = 32


def _safe_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if (
        not normalized
        or _SECRET_SHAPE.search(normalized)
        or _PATH_SHAPE.search(normalized)
    ):
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
        elif (
            key in _INTEGER_KEYS
            and isinstance(value, int)
            and not isinstance(value, bool)
        ):
            if value >= 0:
                sanitized[key] = value
        elif key in _BOOLEAN_KEYS and isinstance(value, bool):
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


def sanitize_metric_attributes(
    attributes: Mapping[str, Any] | None,
) -> dict[str, str | bool | int | tuple[str, ...]]:
    """Return bounded attributes with all correlation identifiers removed."""
    return {
        key: value
        for key, value in sanitize_attributes(attributes).items()
        if key not in _CORRELATION_KEYS
    }
