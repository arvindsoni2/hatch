from __future__ import annotations

import ast
from pathlib import Path

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from app.config import settings
from app.services.coach_conversation_state import (
    TRANSITIONS,
    allowed_commands,
    require_transition,
)
from app.services.coach_conversational_contracts import (
    CONVERSATION_COMMAND_CONTRACT,
    CONVERSATION_COMMAND_RESULT_CONTRACT,
    DELIVERY_POLICY,
    ERROR_REGISTRY,
    EVIDENCE_GROUNDING_CONTRACT,
    FOLLOW_UP_CONTRACT,
    LIVE_VIEW_CONTRACT,
    PROGRESS_CONTRACT,
    REPORT_CONTRACT,
    RUBRIC_CONTRACT,
    SESSION_PLAN_CONTRACT,
)

Settings = type(settings)


APPENDIX_A_PROJECTIONS: dict[tuple[str, str], frozenset[str]] = {
    ("planning", "setup"): frozenset(),
    ("ready", "setup"): frozenset({"start", "rebuild_plan", "update_retention"}),
    ("asking", "active"): frozenset(
        {
            "begin_answer",
            "request_hint",
            "skip_question",
            "pause",
            "end_session",
            "update_retention",
        }
    ),
    ("listening", "active"): frozenset(
        {
            "finish_answer",
            "keep_speaking",
            "request_hint",
            "pause",
            "cancel_attempt",
            "update_retention",
        }
    ),
    ("processing_answer", "active"): frozenset(),
    ("awaiting_next_action", "active"): frozenset(
        {
            "request_coaching",
            "retry_answer",
            "edit_transcript",
            "accept_attempt",
            "record_self_assessment",
            "update_retention",
            "pause",
            "end_session",
            "delete_audio",
            "delete_transcript",
        }
    ),
    ("coaching", "active"): frozenset(
        {
            "return_to_review",
            "edit_transcript",
            "retry_answer",
            "accept_attempt",
            "record_self_assessment",
            "update_retention",
            "pause",
            "end_session",
            "delete_audio",
            "delete_transcript",
        }
    ),
    ("asking_follow_up", "active"): frozenset(),
    ("advancing", "active"): frozenset(),
    ("paused", "active"): frozenset(
        {"resume", "update_retention", "end_session", "delete_audio"}
    ),
    ("reporting", "active"): frozenset(),
    ("completed", "completed"): frozenset(
        {
            "record_self_assessment",
            "retry_report",
            "delete_audio",
            "delete_transcript",
        }
    ),
    ("recoverable_error", "setup"): frozenset({"retry_setup", "update_retention"}),
    ("recoverable_error", "active"): frozenset(
        {
            "retry_processing",
            "retry_answer",
            "retry_report",
            "update_retention",
            "pause",
            "end_session",
            "delete_audio",
            "delete_transcript",
        }
    ),
    ("abandoned", "abandoned"): frozenset(),
    ("failed", "failed"): frozenset(),
}


EXPECTED_ERROR_HTTP_STATUSES = {
    "coach_conversation_not_enabled": 403,
    "coach_conversational_command_required": 409,
    "coach_conversation_invalid_state": 409,
    "coach_conversation_version_conflict": 409,
    "coach_command_idempotency_conflict": 409,
    "coach_contract_unsupported": 400,
    "coach_setup_claim_expired": 409,
    "coach_setup_retry_budget_exhausted": 409,
    "coach_plan_rebuild_not_allowed": 409,
    "coach_attempt_not_active": 409,
    "coach_attempt_client_id_conflict": 409,
    "coach_attempt_already_accepted": 409,
    "coach_attempt_limit_exhausted": 409,
    "coach_attempt_upload_required": 409,
    "coach_attempt_upload_conflict": 409,
    "coach_attempt_upload_missing": 404,
    "coach_attempt_upload_hash_mismatch": 422,
    "coach_audio_upload_idempotency_conflict": 409,
    "coach_attempt_retry_budget_exhausted": 409,
    "coach_attempt_retry_source_unavailable": 409,
    "coach_attempt_job_budget_exhausted": 409,
    "coach_attempt_stale_claim": 409,
    "coach_transcript_deleted": 409,
    "coach_transcript_version_conflict": 409,
    "coach_transcript_schema_invalid": 422,
    "coach_evaluation_unavailable": 503,
    "coach_evaluation_evidence_span_invalid": 422,
    "coach_evaluation_prohibited_inference": 422,
    "coach_grounding_evidence_id_invalid": 422,
    "coach_grounding_source_unavailable": 503,
    "coach_draft_evidence_consent_required": 422,
    "coach_followup_budget_exhausted": 409,
    "coach_followup_reason_invalid": 422,
    "coach_followup_transcript_ungrounded": 422,
    "coach_followup_duplicate": 409,
    "coach_audio_already_deleted": 409,
    "coach_audio_cleanup_failed": 503,
    "coach_audio_deletion_failed": 503,
    "coach_export_source_changed": 409,
    "coach_report_unavailable": 409,
    "coach_report_not_ready": 409,
    "coach_report_invalidated": 409,
    "coach_report_conversational_snapshot_stale": 409,
    "coach_conversational_session_retry_unsupported": 409,
    "coach_progress_selector_conflict": 400,
    "coach_progress_incompatible_session": 409,
    "coach_locale_unsupported": 422,
    "coach_session_deletion_in_progress": 409,
    "coach_session_deletion_failed": 503,
    "coach_deletion_claim_expired": 409,
}


EXPECTED_RETRYABLE_ERRORS = frozenset(
    {
        "coach_setup_claim_expired",
        "coach_evaluation_unavailable",
        "coach_grounding_source_unavailable",
        "coach_audio_cleanup_failed",
        "coach_audio_deletion_failed",
        "coach_export_source_changed",
        "coach_report_conversational_snapshot_stale",
        "coach_session_deletion_failed",
        "coach_deletion_claim_expired",
    }
)


@dataclass
class SessionStateFixture:
    conversation_state: str | None
    status: str


def test_public_contract_registries_are_runtime_read_only() -> None:
    with pytest.raises(TypeError):
        TRANSITIONS["start"] = TRANSITIONS["start"]  # type: ignore[index]
    with pytest.raises(TypeError):
        ERROR_REGISTRY["coach_conversation_version_conflict"] = ERROR_REGISTRY[
            "coach_conversation_version_conflict"
        ]  # type: ignore[index]

    assert "start" in allowed_commands(state="ready", status="setup")
    assert ERROR_REGISTRY["coach_conversation_version_conflict"].http_status == 409


def test_session_object_drives_allowed_commands_and_required_transition() -> None:
    session = SessionStateFixture(conversation_state="ready", status="setup")

    assert allowed_commands(session) == ("start", "rebuild_plan", "update_retention")
    assert require_transition(session, "start") is TRANSITIONS["start"]


@pytest.mark.parametrize(
    "session",
    [
        SessionStateFixture(conversation_state=None, status="setup"),
        SessionStateFixture(conversation_state="not_a_state", status="active"),
        SessionStateFixture(conversation_state="ready", status="not_a_status"),
    ],
)
def test_session_object_with_null_or_invalid_projection_fails_closed(
    session: SessionStateFixture,
) -> None:
    assert allowed_commands(session) == ()
    with pytest.raises(ValueError, match="coach_conversation_invalid_state"):
        require_transition(session, "start")


def test_allowed_commands_are_derived_from_transition_registry() -> None:
    assert allowed_commands(state="ready", status="setup") == (
        "start",
        "rebuild_plan",
        "update_retention",
    )
    assert allowed_commands(state="processing_answer", status="active") == ()
    assert "begin_answer" in allowed_commands(state="asking", status="active")


@pytest.mark.parametrize(
    ("state", "status", "command_type"),
    [
        ("completed", "active", "retry_report"),
        ("completed", "active", "record_self_assessment"),
        ("ready", "active", "update_retention"),
        ("completed", "active", "delete_audio"),
    ],
)
def test_transition_registry_rejects_unlisted_state_status_cross_products(
    state: str, status: str, command_type: str
) -> None:
    assert command_type not in allowed_commands(state=state, status=status)
    with pytest.raises(ValueError, match="coach_conversation_invalid_state"):
        require_transition(state=state, status=status, command_type=command_type)


@pytest.mark.parametrize(
    ("state", "status", "command_type"),
    [
        ("completed", "completed", "retry_report"),
        ("completed", "completed", "record_self_assessment"),
        ("ready", "setup", "update_retention"),
        ("completed", "completed", "delete_audio"),
    ],
)
def test_transition_registry_preserves_valid_exact_pairs(
    state: str, status: str, command_type: str
) -> None:
    assert command_type in allowed_commands(state=state, status=status)
    assert (
        require_transition(state=state, status=status, command_type=command_type)
        is not None
    )


@pytest.mark.parametrize(
    ("state", "status", "expected"),
    [
        (*projection, commands)
        for projection, commands in APPENDIX_A_PROJECTIONS.items()
    ],
)
def test_allowed_commands_match_every_appendix_a_projection(
    state: str, status: str, expected: frozenset[str]
) -> None:
    actual = allowed_commands(state=state, status=status)
    assert frozenset(actual) == expected
    assert len(actual) == len(expected)


def test_all_unlisted_state_status_pairs_are_fail_closed() -> None:
    states = {state for state, _ in APPENDIX_A_PROJECTIONS}
    statuses = {status for _, status in APPENDIX_A_PROJECTIONS}

    for state in states:
        for status in statuses:
            if (state, status) not in APPENDIX_A_PROJECTIONS:
                assert allowed_commands(state=state, status=status) == ()


def test_require_transition_rejects_a_command_outside_its_registered_state() -> None:
    with pytest.raises(ValueError, match="coach_conversation_invalid_state"):
        require_transition(state="ready", status="setup", command_type="begin_answer")


def test_error_registry_is_complete_and_rejects_forbidden_alias() -> None:
    assert {
        code: definition.http_status for code, definition in ERROR_REGISTRY.items()
    } == EXPECTED_ERROR_HTTP_STATUSES
    assert len(ERROR_REGISTRY) == 50
    assert ERROR_REGISTRY["coach_conversational_command_required"].http_status == 409
    assert "coach_progress_incompatible_session" in ERROR_REGISTRY
    assert "coach_session_incompatible_for_progress" not in ERROR_REGISTRY
    assert all(
        item.message and isinstance(item.retryable, bool)
        for item in ERROR_REGISTRY.values()
    )


def test_error_registry_locks_retryability_and_frontend_safe_messages() -> None:
    assert {
        code for code, definition in ERROR_REGISTRY.items() if definition.retryable
    } == EXPECTED_RETRYABLE_ERRORS

    forbidden_message_fragments = (
        "provider",
        "prompt",
        "stack trace",
        "traceback",
        "secret",
        "api key",
        ".env",
        "file://",
    )
    for definition in ERROR_REGISTRY.values():
        message = definition.message
        assert message == message.strip()
        assert 1 <= len(message) <= 120
        assert "/" not in message and "\\" not in message
        assert not any(
            fragment in message.casefold() for fragment in forbidden_message_fragments
        )


def test_canonical_contract_versions_are_centralized() -> None:
    assert CONVERSATION_COMMAND_CONTRACT == "coach_conversation_command_v1"
    assert (
        CONVERSATION_COMMAND_RESULT_CONTRACT == "coach_conversation_command_result_v1"
    )
    assert LIVE_VIEW_CONTRACT == "coach_live_view_v1"
    assert SESSION_PLAN_CONTRACT == "coach_session_plan_v1"
    assert RUBRIC_CONTRACT == "coach_conversational_rubric_v1"
    assert EVIDENCE_GROUNDING_CONTRACT == "coach_evidence_grounding_v1"
    assert FOLLOW_UP_CONTRACT == "coach_follow_up_v1"
    assert REPORT_CONTRACT == "coach_conversational_report_v1"
    assert PROGRESS_CONTRACT == "coach_conversational_progress_v2"
    assert DELIVERY_POLICY == "coach_delivery_policy_v1"


def test_conversational_contract_versions_have_single_production_authority() -> None:
    app_root = Path(__file__).parents[2] / "app"
    authority = app_root / "services" / "coach_conversational_contracts.py"
    canonical_values = {
        "coach_evidence_grounding_v1",
        "coach_follow_up_v1",
        "coach_conversational_report_v1",
    }
    scattered: list[str] = []
    for path in app_root.rglob("*.py"):
        if path == authority:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value in canonical_values:
                scattered.append(f"{path.relative_to(app_root)}:{node.lineno}")
    assert scattered == []


def test_conversational_field_defaults_match_section_36_and_processing_contract() -> (
    None
):
    expected_defaults = {
        "HATCH_COACH_CONVERSATIONAL_ENABLED": False,
        "HATCH_COACH_AUTO_TURN_DETECTION_ENABLED": True,
        "HATCH_COACH_EVIDENCE_GROUNDING_ENABLED": True,
        "HATCH_COACH_CONVERSATIONAL_PROGRESS_ENABLED": True,
        "HATCH_COACH_SILENCE_WARNING_MS": 4000,
        "HATCH_COACH_SILENCE_FINISH_PROMPT_MS": 9000,
        "HATCH_COACH_MAX_ANSWER_DURATION_SECONDS": 600,
        "HATCH_COACH_MAX_ATTEMPTS_PER_QUESTION": 5,
        "HATCH_COACH_MAX_PROCESSING_RETRIES_PER_ATTEMPT": 2,
        "HATCH_COACH_PROGRESS_MAX_GROUPS": 20,
        "HATCH_COACH_MAX_FOLLOWUPS_PER_ROOT": 2,
        "HATCH_COACH_MAX_TRANSCRIPT_CHARACTERS": 30000,
        "HATCH_COACH_MAX_EVIDENCE_CLAIMS": 20,
        "HATCH_COACH_AUDIO_FAILURE_RETENTION_HOURS": 24,
        "HATCH_COACH_TIMEOUT_CONVERSATIONAL_JOB_SECONDS": 900,
        "HATCH_COACH_TIMEOUT_TRANSCRIPTION_SECONDS": 300,
        "HATCH_COACH_TIMEOUT_SPEECH_ANALYSIS_SECONDS": 120,
        "HATCH_COACH_TIMEOUT_CONVERSATIONAL_EVALUATION_SECONDS": 300,
        "HATCH_COACH_TIMEOUT_EVIDENCE_GROUNDING_SECONDS": 180,
        "HATCH_COACH_TIMEOUT_FOLLOWUP_DECISION_SECONDS": 120,
        "HATCH_COACH_TIMEOUT_COACHING_JOB_SECONDS": 240,
        "HATCH_COACH_TIMEOUT_AUDIO_CLEANUP_JOB_SECONDS": 180,
    }
    assert {
        name: Settings.model_fields[name].default for name in expected_defaults
    } == expected_defaults


def test_checked_environment_keeps_conversational_creation_disabled() -> None:
    assert settings.HATCH_COACH_CONVERSATIONAL_ENABLED is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("HATCH_COACH_MAX_ATTEMPTS_PER_QUESTION", 0),
        ("HATCH_COACH_MAX_ATTEMPTS_PER_QUESTION", 21),
        ("HATCH_COACH_MAX_PROCESSING_RETRIES_PER_ATTEMPT", -1),
        ("HATCH_COACH_MAX_PROCESSING_RETRIES_PER_ATTEMPT", 6),
        ("HATCH_COACH_PROGRESS_MAX_GROUPS", 0),
        ("HATCH_COACH_PROGRESS_MAX_GROUPS", 101),
    ],
)
def test_conversational_bounded_settings_reject_out_of_range_values(
    field: str, value: int
) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value})
