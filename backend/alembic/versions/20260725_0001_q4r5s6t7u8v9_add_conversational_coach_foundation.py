"""add conversational coach foundation

Revision ID: q4r5s6t7u8v9
Revises: p3q4r5s6t7u8
Create Date: 2026-07-26 09:41:07.583545+00:00

"""

from __future__ import annotations

import json
import math
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = "q4r5s6t7u8v9"
down_revision: Union[str, None] = "p3q4r5s6t7u8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LEGACY_SCORE_DIMENSIONS = {
    "relevance",
    "star_structure",
    "technical_depth",
    "conciseness",
    "communication",
    "impact_metrics",
}
_DIAGNOSTIC_STAGES = {
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
}
_DIAGNOSTIC_OUTCOMES = {
    "completed",
    "withheld_insufficient_evidence",
    "fallback_deterministic",
    "invalid_output",
    "unavailable",
    "failed",
}
_DIAGNOSTIC_EXECUTION_MODES = {"llm", "deterministic", "cache", "not_run"}
_DIAGNOSTIC_GATE_CODES = {
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
}
_PYDANTIC_INTEGER_STRING = re.compile(r"^[+-]?[0-9]+(?:_[0-9]+)*(?:\.0+)?$")
_PYDANTIC_UNSIGNED_INTEGER_REMAINDER = re.compile(
    r"^(?:0|[1-9][0-9]*(?:_[0-9]+)*)(?:\.0+)?$"
)
_PYDANTIC_FLOAT_STRING = re.compile(
    r"^[+-]?(?:"
    r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
    r"|inf(?:inity)?|nan)$",
    re.IGNORECASE,
)
_RUST_CHAR_WHITESPACE = (
    "\u0009\u000a\u000b\u000c\u000d\u0020\u0085\u00a0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000"
)


def _trim_rust_whitespace(value: str) -> str:
    return value.strip(_RUST_CHAR_WHITESPACE)


def _coerce_pydantic_integer(value: object) -> int | None:
    """Mirror Pydantic v2 lax integers for JSON-native persisted values."""
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if math.isfinite(value) and value.is_integer() else None
    if isinstance(value, str):
        normalized = _trim_rust_whitespace(value)
        if _PYDANTIC_INTEGER_STRING.fullmatch(normalized):
            integer_part = normalized.partition(".")[0].replace("_", "")
        else:
            outer_sign = ""
            body = normalized
            if body.startswith(("+", "-")):
                outer_sign, body = body[0], body[1:]
            if not body.startswith("0"):
                return None
            prefix_end = 0
            while prefix_end < len(body) and body[prefix_end] in {"0", "_"}:
                prefix_end += 1
            remainder = body[prefix_end:]
            if not remainder:
                if not body.endswith("0"):
                    return None
                integer_part = "0"
            elif remainder.startswith("-") and outer_sign != "-":
                magnitude = remainder[1:]
                if magnitude.startswith("_"):
                    magnitude = magnitude[1:]
                if not _PYDANTIC_UNSIGNED_INTEGER_REMAINDER.fullmatch(magnitude):
                    return None
                integer_part = "-" + magnitude.partition(".")[0].replace("_", "")
            else:
                if not _PYDANTIC_UNSIGNED_INTEGER_REMAINDER.fullmatch(remainder):
                    return None
                integer_part = ("-" if outer_sign == "-" else "") + remainder.partition(
                    "."
                )[0].replace("_", "")
        try:
            return int(integer_part)
        except ValueError:
            return None
    return None


def _coerce_non_negative_integer(value: object) -> int | None:
    number = _coerce_pydantic_integer(value)
    if number is None or number < 0:
        return None
    return number


def _is_valid_diagnostic(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    allowed = {
        "validation_schema_version",
        "stage",
        "outcome",
        "execution_mode",
        "prompt_id",
        "prompt_version",
        "output_schema_version",
        "model_id",
        "attempt_count",
        "repair_count",
        "gate_codes",
        "duration_ms",
    }
    if set(value) - allowed:
        return False
    if value.get("validation_schema_version", "1.0.0") != "1.0.0":
        return False
    if value.get("stage") not in _DIAGNOSTIC_STAGES:
        return False
    if value.get("outcome") not in _DIAGNOSTIC_OUTCOMES:
        return False
    execution_mode = value.get("execution_mode")
    if execution_mode not in _DIAGNOSTIC_EXECUTION_MODES:
        return False
    attempt_count = _coerce_non_negative_integer(value.get("attempt_count"))
    if (
        attempt_count is None
        or _coerce_non_negative_integer(value.get("repair_count")) is None
    ):
        return False
    if _coerce_non_negative_integer(value.get("duration_ms")) is None:
        return False
    gate_codes = value.get("gate_codes")
    if not isinstance(gate_codes, list) or not all(
        code in _DIAGNOSTIC_GATE_CODES for code in gate_codes
    ):
        return False
    prompt_values = tuple(
        value.get(field)
        for field in (
            "prompt_id",
            "prompt_version",
            "output_schema_version",
            "model_id",
        )
    )
    if any(item is not None and not isinstance(item, str) for item in prompt_values):
        return False
    if execution_mode == "llm":
        if (
            not value.get("prompt_id")
            or not value.get("prompt_version")
            or not value.get("model_id")
        ):
            return False
        if attempt_count < 1:
            return False
    elif any(item is not None for item in prompt_values):
        return False
    return True


def _is_valid_rubric(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    dimensions = value.get("dimensions", {})
    if not isinstance(dimensions, dict):
        return False
    for dimension in dimensions.values():
        if not isinstance(dimension, dict):
            return False
        score = _coerce_non_negative_integer(dimension.get("score", 0))
        if score is None or score > 10:
            return False
        if dimension.get("score_band", "needs_work") not in {
            "strong",
            "good",
            "needs_work",
            "weak",
        }:
            return False
        evidence = dimension.get("evidence", [])
        if not isinstance(evidence, list) or not all(
            isinstance(item, str) for item in evidence
        ):
            return False
        if not isinstance(dimension.get("drill", ""), str):
            return False
    if not isinstance(value.get("focus_for_next_session", ""), str):
        return False
    diagnostic = value.get("diagnostic")
    return diagnostic is None or _is_valid_diagnostic(diagnostic)


def _parse_pydantic_float_string(value: str) -> float | None:
    """Snapshot pydantic-core 2.46.4 str_as_float for persisted JSON strings."""
    normalized = _trim_rust_whitespace(value)
    if _PYDANTIC_FLOAT_STRING.fullmatch(normalized):
        return float(normalized)
    if (
        value.startswith("_")
        or value.endswith("_")
        or "_" not in value
        or "__" in value
    ):
        return None
    normalized = value.replace("_", "")
    if not _PYDANTIC_FLOAT_STRING.fullmatch(normalized):
        return None
    return float(normalized)


def _coerce_finite_number(value: object) -> float | None:
    """Mirror Pydantic's finite float coercion without importing app runtime."""
    if isinstance(value, str):
        number = _parse_pydantic_float_string(value)
        return number if number is not None and math.isfinite(number) else None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (OverflowError, TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _is_pydantic_boolean(value: object) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)) and value in {0, 1}:
        return True
    return isinstance(value, str) and value.lower() in {
        "0",
        "1",
        "off",
        "on",
        "false",
        "true",
        "f",
        "t",
        "n",
        "y",
        "no",
        "yes",
    }


def _is_valid_legacy_completed_evaluation(
    evaluation_state: object, evaluation_json: object
) -> bool:
    """Mirror coach_aggregation._parse_completed's persisted validity gates."""
    if evaluation_state != "completed" or not isinstance(evaluation_json, str):
        return False
    try:
        payload = json.loads(evaluation_json)
    except (TypeError, ValueError):
        return False
    if (
        not isinstance(payload, dict)
        or payload.get("evaluation_state", "completed") != "completed"
    ):
        return False
    overall = _coerce_finite_number(payload.get("overall", 0.0))
    if overall is None or not 0 <= overall <= 10:
        return False
    scores = payload.get("scores", {})
    if not isinstance(scores, dict) or set(scores) != _LEGACY_SCORE_DIMENSIONS:
        return False
    for value in scores.values():
        score = _coerce_pydantic_integer(value)
        if score is None or not 0 <= score <= 10:
            return False
    string_fields = ("feedback",)
    if any(
        field in payload and not isinstance(payload[field], str)
        for field in string_fields
    ):
        return False
    list_fields = (
        "strengths",
        "improvements",
        "evidence_references",
        "speech_coaching",
    )
    if any(
        field in payload
        and (
            not isinstance(payload[field], list)
            or not all(isinstance(item, str) for item in payload[field])
        )
        for field in list_fields
    ):
        return False
    if "follow_up_question" in payload and not (
        payload["follow_up_question"] is None
        or isinstance(payload["follow_up_question"], str)
    ):
        return False
    if "diagnostic" in payload and not (
        payload["diagnostic"] is None or _is_valid_diagnostic(payload["diagnostic"])
    ):
        return False
    if "rubric" in payload and not (
        payload["rubric"] is None or _is_valid_rubric(payload["rubric"])
    ):
        return False
    if "retryable" in payload and not _is_pydantic_boolean(payload["retryable"]):
        return False
    return True


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "coach_session_deletion_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_key_hash", sa.String(length=64), nullable=False),
        sa.Column("command_id", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("result_state", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "result_state IN ('processing', 'failed', 'completed')",
            name="ck_deletion_results_state",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_key_hash", "command_id", name="uq_deletion_results_session_command"
        ),
    )
    op.create_table(
        "interview_attempt_evaluations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("recording_id", sa.String(length=36), nullable=False),
        sa.Column("transcript_version_id", sa.String(length=36), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("answer_level", sa.String(length=32), nullable=True),
        sa.Column("rubric_json", sqlite.JSON(), nullable=True),
        sa.Column("evidence_findings_json", sqlite.JSON(), nullable=True),
        sa.Column("coaching_json", sqlite.JSON(), nullable=True),
        sa.Column("follow_up_proposal_json", sqlite.JSON(), nullable=True),
        sa.Column("diagnostics_json", sqlite.JSON(), nullable=True),
        sa.Column("model_route_json", sqlite.JSON(), nullable=True),
        sa.Column("evaluation_contract_version", sa.String(length=64), nullable=False),
        sa.Column("evidence_contract_version", sa.String(length=64), nullable=False),
        sa.Column("follow_up_contract_version", sa.String(length=64), nullable=False),
        sa.Column("async_job_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "state IN ('pending', 'completed', 'unavailable', 'invalid', 'failed', "
            "'superseded', 'deleted')",
            name="ck_attempt_evaluations_state",
        ),
        sa.ForeignKeyConstraint(
            ["recording_id"], ["session_recordings.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["transcript_version_id"],
            ["interview_transcript_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recording_id",
            "version_number",
            name="uq_attempt_evaluations_recording_version",
        ),
    )
    with op.batch_alter_table("interview_attempt_evaluations", schema=None) as batch_op:
        batch_op.create_index(
            "idx_attempt_evaluations_recording_version",
            ["recording_id", "version_number"],
            unique=False,
        )

    op.create_table(
        "interview_transcript_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("recording_id", sa.String(length=36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("edit_reason", sa.String(length=64), nullable=True),
        sa.Column("created_by", sa.String(length=32), nullable=False),
        sa.Column("processing_generation", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "source IN ('transcription', 'candidate_text', 'candidate_edit', "
            "'recovered_transcription')",
            name="ck_transcript_versions_source",
        ),
        sa.CheckConstraint(
            "created_by IN ('system', 'candidate')",
            name="ck_transcript_versions_created_by",
        ),
        sa.ForeignKeyConstraint(
            ["recording_id"], ["session_recordings.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recording_id",
            "version_number",
            name="uq_transcript_versions_recording_version",
        ),
    )
    with op.batch_alter_table("interview_transcript_versions", schema=None) as batch_op:
        batch_op.create_index(
            "idx_transcript_versions_recording_version",
            ["recording_id", "version_number"],
            unique=False,
        )

    op.create_table(
        "interview_attempt_stages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("recording_id", sa.String(length=36), nullable=False),
        sa.Column("evaluation_version_id", sa.String(length=36), nullable=False),
        sa.Column("stage_name", sa.String(length=64), nullable=False),
        sa.Column("stage_state", sa.String(length=32), nullable=False),
        sa.Column(
            "attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "repair_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("claim_token", sa.String(length=64), nullable=True),
        sa.Column("expected_processing_generation", sa.Integer(), nullable=True),
        sa.Column("source_transcript_version_id", sa.String(length=36), nullable=True),
        sa.Column("reused_from_stage_id", sa.String(length=36), nullable=True),
        sa.Column("job_deadline_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("diagnostics_json", sqlite.JSON(), nullable=True),
        sa.CheckConstraint(
            "stage_name IN ('audio_persist', 'transcription', 'speech_analysis', "
            "'content_evaluation', 'evidence_grounding', 'follow_up_decision', "
            "'coaching_enrichment', 'audio_cleanup')",
            name="ck_attempt_stages_name",
        ),
        sa.CheckConstraint(
            "stage_state IN ('not_started', 'pending', 'running', 'completed', "
            "'reused', 'not_applicable', 'unavailable', 'failed_retryable', "
            "'failed_terminal')",
            name="ck_attempt_stages_state",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND repair_count >= 0",
            name="ck_attempt_stages_counts",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_version_id"],
            ["interview_attempt_evaluations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recording_id"], ["session_recordings.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reused_from_stage_id"],
            ["interview_attempt_stages.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recording_id",
            "evaluation_version_id",
            "stage_name",
            name="uq_attempt_stages_recording_evaluation_stage",
        ),
    )
    with op.batch_alter_table("interview_attempt_stages", schema=None) as batch_op:
        batch_op.create_index(
            "idx_attempt_stages_job_state", ["job_id", "stage_state"], unique=False
        )

    op.create_table(
        "interview_attempt_uploads",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("attempt_id", sa.String(length=36), nullable=False),
        sa.Column("upload_id", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("storage_uri", sa.String(length=512), nullable=False),
        sa.Column("result_state", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "result_state IN ('pending', 'completed', 'failed', 'deleted')",
            name="ck_attempt_uploads_state",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"], ["session_recordings.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "attempt_id", "upload_id", name="uq_attempt_uploads_attempt_upload"
        ),
    )
    with op.batch_alter_table("interview_attempt_uploads", schema=None) as batch_op:
        batch_op.create_index(
            "idx_attempt_uploads_attempt_upload",
            ["attempt_id", "upload_id"],
            unique=False,
        )

    op.create_table(
        "coach_conversation_command_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("command_id", sa.String(length=64), nullable=False),
        sa.Column("command_type", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("expected_state_version", sa.Integer(), nullable=False),
        sa.Column("result_state", sa.String(length=32), nullable=False),
        sa.Column("result_json", sqlite.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "result_state IN ('completed', 'accepted_processing', 'duplicate', "
            "'invalid_state', 'version_conflict', 'idempotency_conflict', "
            "'invalid_payload', 'resource_blocked', 'not_found', "
            "'permission_denied', 'stale_claim')",
            name="ck_command_results_state",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["interview_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id", "command_id", name="uq_command_results_session_command"
        ),
    )
    with op.batch_alter_table(
        "coach_conversation_command_results", schema=None
    ) as batch_op:
        batch_op.create_index(
            "idx_command_results_session_command",
            ["session_id", "command_id"],
            unique=False,
        )
        batch_op.create_index(
            "idx_command_results_session_created",
            ["session_id", "created_at"],
            unique=False,
        )

    op.create_table(
        "coach_session_evidence_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("evidence_id", sa.String(length=128), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_record_id", sa.String(length=128), nullable=False),
        sa.Column("source_record_version", sa.String(length=128), nullable=False),
        sa.Column("source_path", sa.String(length=512), nullable=False),
        sa.Column("snapshot_text", sa.Text(), nullable=False),
        sa.Column("approval_state", sa.String(length=32), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "approval_state IN ('approved', 'confirmed', 'reviewed_final', 'reviewed', 'candidate_selected_unapproved', 'draft', 'context_only')",
            name="ck_session_evidence_approval_state",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["interview_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id", "evidence_id", name="uq_session_evidence_session_evidence"
        ),
    )
    with op.batch_alter_table(
        "coach_session_evidence_records", schema=None
    ) as batch_op:
        batch_op.create_index(
            "idx_session_evidence_records_session_evidence",
            ["session_id", "evidence_id"],
            unique=False,
        )

    op.create_table(
        "interview_session_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("state_before", sa.String(length=32), nullable=True),
        sa.Column("state_after", sa.String(length=32), nullable=True),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.String(length=36), nullable=True),
        sa.Column("recording_id", sa.String(length=36), nullable=True),
        sa.Column("command_id", sa.String(length=64), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sqlite.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "actor_type IN ('candidate', 'system', 'worker', 'reconciler', 'migration')",
            name="ck_session_events_actor_type",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["interview_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id", "sequence_number", name="uq_session_events_session_sequence"
        ),
    )
    with op.batch_alter_table("interview_session_events", schema=None) as batch_op:
        batch_op.create_index(
            "idx_session_events_session_created",
            ["session_id", "created_at"],
            unique=False,
        )
        batch_op.create_index(
            "idx_session_events_session_sequence",
            ["session_id", "sequence_number"],
            unique=False,
        )
        batch_op.create_index(
            "idx_session_events_session_type",
            ["session_id", "event_type"],
            unique=False,
        )

    with op.batch_alter_table("interview_sessions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("experience_version", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(
            sa.Column("conversation_state", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(sa.Column("state_version", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("resume_state", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(
            sa.Column("active_question_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("active_recording_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("active_root_question_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(sa.Column("last_activity_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("paused_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("recoverable_error_code", sa.String(length=128), nullable=True)
        )
        batch_op.add_column(
            sa.Column("recoverable_error_scope", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(
            sa.Column("recoverable_error_context_json", sqlite.JSON(), nullable=True)
        )
        batch_op.add_column(sa.Column("setup_generation", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("setup_job_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("setup_claim_token", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(sa.Column("setup_claimed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("setup_claim_expires_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(sa.Column("setup_started_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("setup_completed_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("setup_attempt_count", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("setup_max_attempts", sa.Integer(), nullable=True)
        )
        batch_op.add_column(sa.Column("retention_version", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("deletion_state", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(
            sa.Column("deletion_generation", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("deletion_job_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("deletion_command_id", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("deletion_claim_token", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("deletion_claim_expires_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("deletion_started_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("deletion_failed_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("deletion_error_code", sa.String(length=128), nullable=True)
        )
        batch_op.add_column(sa.Column("event_version", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("planning_request_json", sqlite.JSON(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("session_plan_json", sqlite.JSON(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "session_plan_contract_version", sa.String(length=64), nullable=True
            )
        )
        batch_op.add_column(
            sa.Column(
                "evaluation_contract_version", sa.String(length=64), nullable=True
            )
        )
        batch_op.add_column(
            sa.Column("report_contract_version", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("compatibility_key", sa.String(length=256), nullable=True)
        )
        batch_op.add_column(
            sa.Column("retention_policy_json", sqlite.JSON(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("session_plan_amendment_version", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("report_build_reason", sa.String(length=32), nullable=True)
        )
        batch_op.create_index(
            "idx_interview_sessions_conversation_state",
            ["conversation_state"],
            unique=False,
        )
        batch_op.create_index(
            "idx_interview_sessions_experience_state",
            ["experience_version", "status"],
            unique=False,
        )

    op.execute(
        sa.text(
            """
            UPDATE interview_sessions
            SET experience_version = 'legacy_v1',
                conversation_state = NULL,
                state_version = 0,
                event_version = 0,
                setup_generation = 0,
                setup_attempt_count = 0,
                setup_max_attempts = 3,
                retention_version = 0,
                deletion_state = 'not_requested',
                deletion_generation = 0,
                session_plan_amendment_version = 0
            """
        )
    )

    with op.batch_alter_table("interview_sessions", schema=None) as batch_op:
        batch_op.alter_column(
            "experience_version", nullable=False, server_default=sa.text("'legacy_v1'")
        )
        batch_op.alter_column(
            "state_version", nullable=False, server_default=sa.text("0")
        )
        batch_op.alter_column(
            "setup_generation", nullable=False, server_default=sa.text("0")
        )
        batch_op.alter_column(
            "setup_attempt_count", nullable=False, server_default=sa.text("0")
        )
        batch_op.alter_column(
            "setup_max_attempts", nullable=False, server_default=sa.text("3")
        )
        batch_op.alter_column(
            "retention_version", nullable=False, server_default=sa.text("0")
        )
        batch_op.alter_column(
            "deletion_state", nullable=False, server_default=sa.text("'not_requested'")
        )
        batch_op.alter_column(
            "deletion_generation", nullable=False, server_default=sa.text("0")
        )
        batch_op.alter_column(
            "event_version", nullable=False, server_default=sa.text("0")
        )
        batch_op.alter_column(
            "session_plan_amendment_version",
            nullable=False,
            server_default=sa.text("0"),
        )
        batch_op.drop_constraint("ck_interview_sessions_report_state", type_="check")
        batch_op.create_check_constraint(
            "ck_interview_sessions_report_state",
            "report_state IN ('not_started', 'building', 'completed', 'fallback', 'failed', 'invalidated')",
        )
        batch_op.create_check_constraint(
            "ck_interview_sessions_status",
            "status IN ('setup', 'active', 'completed', 'abandoned', 'failed')",
        )
        batch_op.create_check_constraint(
            "ck_interview_sessions_conversation_state",
            "conversation_state IS NULL OR conversation_state IN "
            "('planning', 'ready', 'asking', 'listening', 'processing_answer', "
            "'awaiting_next_action', 'coaching', 'asking_follow_up', 'advancing', "
            "'paused', 'reporting', 'completed', 'recoverable_error', 'abandoned', 'failed')",
        )
        batch_op.create_check_constraint(
            "ck_interview_sessions_recoverable_error_scope",
            "recoverable_error_scope IS NULL OR recoverable_error_scope IN "
            "('setup', 'attempt_processing', 'initial_report', 'completed_report_rebuild')",
        )
        batch_op.create_check_constraint(
            "ck_interview_sessions_deletion_state",
            "deletion_state IN ('not_requested', 'deleting', 'failed')",
        )

    with op.batch_alter_table("session_questions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("question_kind", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(
            sa.Column("root_question_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("parent_question_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(sa.Column("follow_up_depth", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("follow_up_reason", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("follow_up_target_dimension", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("follow_up_aggregation_role", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "follow_up_source_recording_id", sa.String(length=36), nullable=True
            )
        )
        batch_op.add_column(
            sa.Column(
                "follow_up_source_transcript_version_id",
                sa.String(length=36),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("follow_up_context_json", sqlite.JSON(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("follow_up_generation_json", sqlite.JSON(), nullable=True)
        )
        batch_op.add_column(sa.Column("source_deleted", sa.Boolean(), nullable=True))
        batch_op.add_column(
            sa.Column("question_state", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(
            sa.Column("accepted_recording_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("attempts_created_count", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("acceptance_generation", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("last_accepted_generation", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "question_category_contract_version",
                sa.String(length=64),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("pending_hint_count", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("pending_hint_types_json", sqlite.JSON(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("question_contract_version", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(sa.Column("asked_sequence", sa.Integer(), nullable=True))

    with op.batch_alter_table("session_recordings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("attempt_number", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("attempt_kind", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(
            sa.Column("retry_of_recording_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("attempt_state", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(sa.Column("attempt_version", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("processing_generation", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("processing_retry_count", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("processing_retry_limit", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "current_transcript_version_id", sa.String(length=36), nullable=True
            )
        )
        batch_op.add_column(
            sa.Column(
                "current_evaluation_version_id", sa.String(length=36), nullable=True
            )
        )
        batch_op.add_column(sa.Column("accepted_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("submitted_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("processing_started_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("processing_completed_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("audio_retention_policy", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(
            sa.Column("audio_retention_state", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(sa.Column("audio_deleted_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("audio_content_hash", sa.String(length=128), nullable=True)
        )
        batch_op.add_column(
            sa.Column("client_attempt_id", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(sa.Column("hint_count", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("self_assessment_json", sqlite.JSON(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("self_assessment_updated_at", sa.DateTime(), nullable=True)
        )

    op.execute(
        sa.text(
            """
            UPDATE session_recordings AS recording
            SET attempt_number = (
                    SELECT COUNT(*)
                    FROM session_recordings AS earlier
                    WHERE earlier.question_id = recording.question_id
                      AND (
                          earlier.created_at < recording.created_at
                          OR (earlier.created_at = recording.created_at AND earlier.id <= recording.id)
                      )
                ),
                attempt_version = 0,
                processing_generation = 0,
                processing_retry_count = 0,
                processing_retry_limit = 0,
                hint_count = 0
            WHERE recording.question_id IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE session_recordings
            SET attempt_version = 0,
                processing_generation = 0,
                processing_retry_count = 0,
                processing_retry_limit = 0,
                hint_count = 0
            WHERE question_id IS NULL
            """
        )
    )
    connection = op.get_bind()
    valid_question_ids = sorted(
        {
            str(row.question_id)
            for row in connection.execute(
                sa.text(
                    """
                    SELECT question_id, evaluation_state, evaluation_json
                    FROM session_recordings
                    WHERE question_id IS NOT NULL AND evaluation_state = 'completed'
                    """
                )
            )
            if _is_valid_legacy_completed_evaluation(
                row.evaluation_state, row.evaluation_json
            )
        }
    )
    op.create_table(
        "_coach_valid_legacy_completed_questions",
        sa.Column("question_id", sa.String(length=36), primary_key=True),
    )
    if valid_question_ids:
        connection.execute(
            sa.text(
                """
                INSERT INTO _coach_valid_legacy_completed_questions(question_id)
                VALUES (:question_id)
                """
            ),
            [{"question_id": question_id} for question_id in valid_question_ids],
        )
    op.execute(
        sa.text(
            """
            UPDATE session_recordings
            SET attempt_kind = CASE WHEN attempt_number = 1 THEN 'primary' ELSE 'retry' END
            WHERE attempt_number IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE session_questions AS question
            SET question_kind = 'planned',
                follow_up_depth = 0,
                source_deleted = 0,
                attempts_created_count = 0,
                acceptance_generation = 0,
                pending_hint_count = 0,
                question_state = CASE
                    WHEN (
                        SELECT CASE
                            WHEN latest.evaluation_state = 'skipped'
                                 OR latest.transcript = '[SKIPPED]'
                            THEN 1 ELSE 0
                        END
                        FROM session_recordings AS latest
                        WHERE latest.question_id = question.id
                          AND (
                              latest.evaluation_state IN
                                  ('completed', 'unavailable', 'invalid', 'skipped', 'failed')
                              OR latest.transcript = '[SKIPPED]'
                          )
                        ORDER BY latest.created_at DESC, latest.id DESC
                        LIMIT 1
                    ) = 1 THEN 'skipped'
                    WHEN EXISTS (
                        SELECT 1 FROM _coach_valid_legacy_completed_questions AS completed
                        WHERE completed.question_id = question.id
                    ) THEN 'answered'
                    ELSE 'pending'
                END,
                accepted_recording_id = NULL
            """
        )
    )
    op.drop_table("_coach_valid_legacy_completed_questions")

    with op.batch_alter_table("session_questions", schema=None) as batch_op:
        batch_op.alter_column(
            "question_kind", nullable=False, server_default=sa.text("'planned'")
        )
        batch_op.alter_column(
            "follow_up_depth", nullable=False, server_default=sa.text("0")
        )
        batch_op.alter_column(
            "source_deleted", nullable=False, server_default=sa.text("0")
        )
        batch_op.alter_column(
            "question_state", nullable=False, server_default=sa.text("'pending'")
        )
        batch_op.alter_column(
            "attempts_created_count", nullable=False, server_default=sa.text("0")
        )
        batch_op.alter_column(
            "acceptance_generation", nullable=False, server_default=sa.text("0")
        )
        batch_op.alter_column(
            "pending_hint_count", nullable=False, server_default=sa.text("0")
        )
        batch_op.create_index(
            "idx_session_questions_root_question", ["root_question_id"], unique=False
        )
        batch_op.create_index(
            "idx_session_questions_session_asked_sequence",
            ["session_id", "asked_sequence"],
            unique=False,
        )
        batch_op.create_unique_constraint(
            "uq_session_questions_session_asked_sequence",
            ["session_id", "asked_sequence"],
        )
        batch_op.create_foreign_key(
            "fk_session_questions_follow_up_recording",
            "session_recordings",
            ["follow_up_source_recording_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_session_questions_follow_up_transcript",
            "interview_transcript_versions",
            ["follow_up_source_transcript_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_session_questions_parent_question",
            "session_questions",
            ["parent_question_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_session_questions_root_question",
            "session_questions",
            ["root_question_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_session_questions_accepted_recording",
            "session_recordings",
            ["accepted_recording_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_check_constraint(
            "ck_session_questions_follow_up_depth",
            "follow_up_depth >= 0 AND follow_up_depth <= 2",
        )
        batch_op.create_check_constraint(
            "ck_session_questions_question_kind",
            "question_kind IN ('planned', 'adaptive_follow_up')",
        )
        batch_op.create_check_constraint(
            "ck_session_questions_question_state",
            "question_state IN ('pending', 'asked', 'answered', 'skipped')",
        )
        batch_op.create_check_constraint(
            "ck_session_questions_follow_up_reason",
            "follow_up_reason IS NULL OR follow_up_reason IN "
            "('clarify_example', 'measurable_result', 'personal_action', 'reasoning', "
            "'role_depth', 'resolve_ambiguity', 'evidence_consistency')",
        )
        batch_op.create_check_constraint(
            "ck_session_questions_attempts_created_count", "attempts_created_count >= 0"
        )
        batch_op.create_check_constraint(
            "ck_session_questions_acceptance_generation", "acceptance_generation >= 0"
        )
        batch_op.create_check_constraint(
            "ck_session_questions_pending_hint_count", "pending_hint_count >= 0"
        )
        batch_op.create_check_constraint(
            "ck_session_questions_kind_depth",
            "(question_kind = 'planned' AND follow_up_depth = 0) OR "
            "(question_kind = 'adaptive_follow_up' AND root_question_id IS NOT NULL "
            "AND parent_question_id IS NOT NULL AND follow_up_depth BETWEEN 1 AND 2)",
        )
        batch_op.create_check_constraint(
            "ck_session_questions_accepted_generation_order",
            "last_accepted_generation IS NULL OR "
            "last_accepted_generation <= acceptance_generation",
        )
        batch_op.create_check_constraint(
            "ck_session_questions_accepted_generation_current",
            "accepted_recording_id IS NULL OR "
            "last_accepted_generation = acceptance_generation",
        )

    with op.batch_alter_table("session_recordings", schema=None) as batch_op:
        batch_op.alter_column(
            "attempt_version", nullable=False, server_default=sa.text("0")
        )
        batch_op.alter_column(
            "processing_generation", nullable=False, server_default=sa.text("0")
        )
        batch_op.alter_column(
            "processing_retry_count", nullable=False, server_default=sa.text("0")
        )
        batch_op.alter_column(
            "processing_retry_limit", nullable=False, server_default=sa.text("0")
        )
        batch_op.alter_column("hint_count", nullable=False, server_default=sa.text("0"))
        batch_op.create_index(
            "idx_session_recordings_async_job_state",
            ["async_job_id", "attempt_state"],
            unique=False,
        )
        batch_op.create_index(
            "idx_session_recordings_question_attempt",
            ["question_id", "attempt_number"],
            unique=False,
        )
        batch_op.create_unique_constraint(
            "uq_session_recordings_question_attempt", ["question_id", "attempt_number"]
        )
        batch_op.create_unique_constraint(
            "uq_session_recordings_session_client_attempt",
            ["session_id", "client_attempt_id"],
        )
        batch_op.create_foreign_key(
            "fk_session_recordings_current_transcript",
            "interview_transcript_versions",
            ["current_transcript_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_session_recordings_current_evaluation",
            "interview_attempt_evaluations",
            ["current_evaluation_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_session_recordings_retry_of",
            "session_recordings",
            ["retry_of_recording_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_check_constraint(
            "ck_session_recordings_attempt_number",
            "attempt_number IS NULL OR attempt_number > 0",
        )
        batch_op.create_check_constraint(
            "ck_session_recordings_processing_retry_count",
            "processing_retry_count >= 0",
        )
        batch_op.create_check_constraint(
            "ck_session_recordings_processing_retry_limit",
            "processing_retry_limit >= 0",
        )
        batch_op.create_check_constraint(
            "ck_session_recordings_hint_count", "hint_count >= 0"
        )
        batch_op.create_check_constraint(
            "ck_session_recordings_attempt_kind",
            "attempt_kind IS NULL OR attempt_kind IN ('primary', 'retry', 'follow_up')",
        )
        batch_op.create_check_constraint(
            "ck_session_recordings_attempt_state",
            "attempt_state IS NULL OR attempt_state IN "
            "('draft', 'uploaded', 'pending_processing', 'completed', "
            "'recoverable_error', 'unavailable', 'invalid', 'cancelled', "
            "'deleted', 'skipped')",
        )
        batch_op.create_check_constraint(
            "ck_session_recordings_retry_budget",
            "processing_retry_count <= processing_retry_limit",
        )

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("session_recordings", schema=None) as batch_op:
        batch_op.drop_constraint("ck_session_recordings_attempt_kind", type_="check")
        batch_op.drop_constraint("ck_session_recordings_attempt_state", type_="check")
        batch_op.drop_constraint("ck_session_recordings_retry_budget", type_="check")
        batch_op.drop_constraint("ck_session_recordings_attempt_number", type_="check")
        batch_op.drop_constraint(
            "ck_session_recordings_processing_retry_count", type_="check"
        )
        batch_op.drop_constraint(
            "ck_session_recordings_processing_retry_limit", type_="check"
        )
        batch_op.drop_constraint("ck_session_recordings_hint_count", type_="check")
        batch_op.drop_constraint(
            "fk_session_recordings_current_transcript", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_session_recordings_current_evaluation", type_="foreignkey"
        )
        batch_op.drop_constraint("fk_session_recordings_retry_of", type_="foreignkey")
        batch_op.drop_constraint(
            "uq_session_recordings_session_client_attempt", type_="unique"
        )
        batch_op.drop_constraint(
            "uq_session_recordings_question_attempt", type_="unique"
        )
        batch_op.drop_index("idx_session_recordings_question_attempt")
        batch_op.drop_index("idx_session_recordings_async_job_state")
        batch_op.drop_column("self_assessment_updated_at")
        batch_op.drop_column("self_assessment_json")
        batch_op.drop_column("hint_count")
        batch_op.drop_column("client_attempt_id")
        batch_op.drop_column("audio_content_hash")
        batch_op.drop_column("audio_deleted_at")
        batch_op.drop_column("audio_retention_state")
        batch_op.drop_column("audio_retention_policy")
        batch_op.drop_column("processing_completed_at")
        batch_op.drop_column("processing_started_at")
        batch_op.drop_column("submitted_at")
        batch_op.drop_column("accepted_at")
        batch_op.drop_column("current_evaluation_version_id")
        batch_op.drop_column("current_transcript_version_id")
        batch_op.drop_column("processing_retry_limit")
        batch_op.drop_column("processing_retry_count")
        batch_op.drop_column("processing_generation")
        batch_op.drop_column("attempt_version")
        batch_op.drop_column("attempt_state")
        batch_op.drop_column("retry_of_recording_id")
        batch_op.drop_column("attempt_kind")
        batch_op.drop_column("attempt_number")

    with op.batch_alter_table("session_questions", schema=None) as batch_op:
        batch_op.drop_constraint("ck_session_questions_kind_depth", type_="check")
        batch_op.drop_constraint(
            "ck_session_questions_accepted_generation_order", type_="check"
        )
        batch_op.drop_constraint(
            "ck_session_questions_accepted_generation_current", type_="check"
        )
        batch_op.drop_constraint("ck_session_questions_follow_up_depth", type_="check")
        batch_op.drop_constraint("ck_session_questions_question_kind", type_="check")
        batch_op.drop_constraint("ck_session_questions_question_state", type_="check")
        batch_op.drop_constraint("ck_session_questions_follow_up_reason", type_="check")
        batch_op.drop_constraint(
            "ck_session_questions_attempts_created_count", type_="check"
        )
        batch_op.drop_constraint(
            "ck_session_questions_acceptance_generation", type_="check"
        )
        batch_op.drop_constraint(
            "ck_session_questions_pending_hint_count", type_="check"
        )
        batch_op.drop_constraint(
            "fk_session_questions_follow_up_recording", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_session_questions_follow_up_transcript", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_session_questions_parent_question", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_session_questions_root_question", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_session_questions_accepted_recording", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "uq_session_questions_session_asked_sequence", type_="unique"
        )
        batch_op.drop_index("idx_session_questions_session_asked_sequence")
        batch_op.drop_index("idx_session_questions_root_question")
        batch_op.drop_column("asked_sequence")
        batch_op.drop_column("question_contract_version")
        batch_op.drop_column("pending_hint_types_json")
        batch_op.drop_column("pending_hint_count")
        batch_op.drop_column("question_category_contract_version")
        batch_op.drop_column("last_accepted_generation")
        batch_op.drop_column("acceptance_generation")
        batch_op.drop_column("attempts_created_count")
        batch_op.drop_column("accepted_recording_id")
        batch_op.drop_column("question_state")
        batch_op.drop_column("source_deleted")
        batch_op.drop_column("follow_up_generation_json")
        batch_op.drop_column("follow_up_context_json")
        batch_op.drop_column("follow_up_source_transcript_version_id")
        batch_op.drop_column("follow_up_source_recording_id")
        batch_op.drop_column("follow_up_aggregation_role")
        batch_op.drop_column("follow_up_target_dimension")
        batch_op.drop_column("follow_up_reason")
        batch_op.drop_column("follow_up_depth")
        batch_op.drop_column("parent_question_id")
        batch_op.drop_column("root_question_id")
        batch_op.drop_column("question_kind")

    op.execute(
        sa.text(
            """
            UPDATE interview_sessions
            SET report_state = 'failed',
                report_json = NULL,
                report_job_id = NULL,
                report_started_at = NULL,
                report_build_reason = NULL
            WHERE report_state = 'invalidated'
            """
        )
    )

    with op.batch_alter_table("interview_sessions", schema=None) as batch_op:
        batch_op.drop_constraint("ck_interview_sessions_deletion_state", type_="check")
        batch_op.drop_constraint(
            "ck_interview_sessions_recoverable_error_scope", type_="check"
        )
        batch_op.drop_constraint(
            "ck_interview_sessions_conversation_state", type_="check"
        )
        batch_op.drop_constraint("ck_interview_sessions_status", type_="check")
        batch_op.drop_constraint("ck_interview_sessions_report_state", type_="check")
        batch_op.create_check_constraint(
            "ck_interview_sessions_report_state",
            "report_state IN ('not_started', 'building', 'completed', 'fallback', 'failed')",
        )
        batch_op.drop_index("idx_interview_sessions_experience_state")
        batch_op.drop_index("idx_interview_sessions_conversation_state")
        batch_op.drop_column("report_build_reason")
        batch_op.drop_column("session_plan_amendment_version")
        batch_op.drop_column("retention_policy_json")
        batch_op.drop_column("compatibility_key")
        batch_op.drop_column("report_contract_version")
        batch_op.drop_column("evaluation_contract_version")
        batch_op.drop_column("session_plan_contract_version")
        batch_op.drop_column("session_plan_json")
        batch_op.drop_column("planning_request_json")
        batch_op.drop_column("event_version")
        batch_op.drop_column("deletion_error_code")
        batch_op.drop_column("deletion_failed_at")
        batch_op.drop_column("deletion_started_at")
        batch_op.drop_column("deletion_claim_expires_at")
        batch_op.drop_column("deletion_claim_token")
        batch_op.drop_column("deletion_command_id")
        batch_op.drop_column("deletion_job_id")
        batch_op.drop_column("deletion_generation")
        batch_op.drop_column("deletion_state")
        batch_op.drop_column("retention_version")
        batch_op.drop_column("setup_max_attempts")
        batch_op.drop_column("setup_attempt_count")
        batch_op.drop_column("setup_completed_at")
        batch_op.drop_column("setup_started_at")
        batch_op.drop_column("setup_claim_expires_at")
        batch_op.drop_column("setup_claimed_at")
        batch_op.drop_column("setup_claim_token")
        batch_op.drop_column("setup_job_id")
        batch_op.drop_column("setup_generation")
        batch_op.drop_column("recoverable_error_context_json")
        batch_op.drop_column("recoverable_error_scope")
        batch_op.drop_column("recoverable_error_code")
        batch_op.drop_column("paused_at")
        batch_op.drop_column("last_activity_at")
        batch_op.drop_column("active_root_question_id")
        batch_op.drop_column("active_recording_id")
        batch_op.drop_column("active_question_id")
        batch_op.drop_column("resume_state")
        batch_op.drop_column("state_version")
        batch_op.drop_column("conversation_state")
        batch_op.drop_column("experience_version")

    with op.batch_alter_table("interview_session_events", schema=None) as batch_op:
        batch_op.drop_index("idx_session_events_session_type")
        batch_op.drop_index("idx_session_events_session_sequence")
        batch_op.drop_index("idx_session_events_session_created")

    op.drop_table("interview_session_events")
    with op.batch_alter_table(
        "coach_session_evidence_records", schema=None
    ) as batch_op:
        batch_op.drop_index("idx_session_evidence_records_session_evidence")

    op.drop_table("coach_session_evidence_records")
    with op.batch_alter_table(
        "coach_conversation_command_results", schema=None
    ) as batch_op:
        batch_op.drop_index("idx_command_results_session_created")
        batch_op.drop_index("idx_command_results_session_command")

    op.drop_table("coach_conversation_command_results")
    with op.batch_alter_table("interview_attempt_uploads", schema=None) as batch_op:
        batch_op.drop_index("idx_attempt_uploads_attempt_upload")

    op.drop_table("interview_attempt_uploads")
    with op.batch_alter_table("interview_attempt_stages", schema=None) as batch_op:
        batch_op.drop_index("idx_attempt_stages_job_state")

    op.drop_table("interview_attempt_stages")
    with op.batch_alter_table("interview_attempt_evaluations", schema=None) as batch_op:
        batch_op.drop_index("idx_attempt_evaluations_recording_version")

    op.drop_table("interview_attempt_evaluations")
    with op.batch_alter_table("interview_transcript_versions", schema=None) as batch_op:
        batch_op.drop_index("idx_transcript_versions_recording_version")

    op.drop_table("interview_transcript_versions")
    op.drop_table("coach_session_deletion_results")
    # ### end Alembic commands ###
