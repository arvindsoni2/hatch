"""Boundary tests for the conversational command and live-view schemas."""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from app.schemas.coach_conversation import (
    AcceptAttemptPayload,
    BeginAnswerPayload,
    CancelAttemptPayload,
    ConversationCommandRequest,
    ConversationCommandResult,
    ConversationErrorResponse,
    ConversationLiveView,
    DeleteAudioPayload,
    DeleteTranscriptPayload,
    EditTranscriptPayload,
    EndSessionPayload,
    FinishAnswerPayload,
    KeepSpeakingPayload,
    PausePayload,
    RebuildPlanPayload,
    RecordSelfAssessmentPayload,
    RequestCoachingPayload,
    RequestHintPayload,
    ResumePayload,
    RetryAnswerPayload,
    RetryProcessingPayload,
    RetryReportPayload,
    RetrySetupPayload,
    ReturnToReviewPayload,
    SkipQuestionPayload,
    StartPayload,
    UpdateRetentionPayload,
)


COMMAND_CONTRACT = "coach_conversation_command_v1"


def command(command_type: str, payload: dict | None = None) -> dict:
    return {
        "command_id": "01JEXAMPLE0000000000000000",
        "command_type": command_type,
        "expected_state_version": 0,
        "payload": payload or {},
        "contract_version": COMMAND_CONTRACT,
    }


COMMAND_CASES = [
    ("start", {}, StartPayload),
    (
        "begin_answer",
        {"recording_type": "audio", "client_attempt_id": "attempt-client_1"},
        BeginAnswerPayload,
    ),
    (
        "finish_answer",
        {"attempt_id": "attempt_1", "transcript": "An answer"},
        FinishAnswerPayload,
    ),
    ("keep_speaking", {"attempt_id": "attempt_1"}, KeepSpeakingPayload),
    ("pause", {}, PausePayload),
    ("resume", {}, ResumePayload),
    ("cancel_attempt", {"attempt_id": "attempt_1"}, CancelAttemptPayload),
    ("retry_answer", {"question_id": "question_1"}, RetryAnswerPayload),
    ("retry_setup", {}, RetrySetupPayload),
    ("rebuild_plan", {"refresh_sources": True}, RebuildPlanPayload),
    ("retry_processing", {}, RetryProcessingPayload),
    ("retry_report", {}, RetryReportPayload),
    ("request_hint", {"hint_type": "star_structure"}, RequestHintPayload),
    ("request_coaching", {"attempt_id": "attempt_1"}, RequestCoachingPayload),
    ("return_to_review", {}, ReturnToReviewPayload),
    (
        "edit_transcript",
        {
            "attempt_id": "attempt_1",
            "transcript": "Corrected answer",
            "edit_reason": "transcription_error",
        },
        EditTranscriptPayload,
    ),
    ("accept_attempt", {"attempt_id": "attempt_1"}, AcceptAttemptPayload),
    (
        "record_self_assessment",
        {
            "attempt_id": "attempt_1",
            "comfort_level": "medium",
            "felt_complete": True,
            "note": "I missed one detail.",
        },
        RecordSelfAssessmentPayload,
    ),
    ("update_retention", {"audio": "retain_until_deleted"}, UpdateRetentionPayload),
    ("skip_question", {}, SkipQuestionPayload),
    (
        "end_session",
        {
            "unaccepted_attempt_action": "accept_attempt",
            "attempt_id": "attempt_1",
            "paused_draft_action": None,
        },
        EndSessionPayload,
    ),
    ("delete_audio", {"attempt_id": "attempt_1"}, DeleteAudioPayload),
    ("delete_transcript", {"attempt_id": "attempt_1"}, DeleteTranscriptPayload),
]


@pytest.mark.parametrize(("command_type", "payload", "payload_type"), COMMAND_CASES)
def test_all_23_commands_dispatch_to_a_strict_typed_payload(
    command_type: str, payload: dict, payload_type: type
) -> None:
    parsed = ConversationCommandRequest.model_validate(command(command_type, payload))

    assert type(parsed.payload) is payload_type
    with pytest.raises(ValidationError):
        ConversationCommandRequest.model_validate(
            command(command_type, {**payload, "unknown": True})
        )


def test_command_envelope_forbids_extra_fields_and_mismatched_payloads() -> None:
    with pytest.raises(ValidationError):
        ConversationCommandRequest.model_validate({**command("start"), "unknown": True})
    with pytest.raises(ValidationError):
        ConversationCommandRequest.model_validate(
            command("accept_attempt", {"hint_type": "star_structure"})
        )


def test_malformed_command_discriminator_returns_validation_error() -> None:
    payload = command("start")
    payload["command_type"] = ["start"]

    with pytest.raises(ValidationError):
        ConversationCommandRequest.model_validate(payload)


@pytest.mark.parametrize(
    "command_id",
    ["", "unsafe/id", "contains space", "x" * 65],
)
def test_command_id_must_be_a_bounded_safe_token(command_id: str) -> None:
    payload = command("start")
    payload["command_id"] = command_id

    with pytest.raises(ValidationError):
        ConversationCommandRequest.model_validate(payload)


def test_command_rejects_negative_versions_and_unsupported_contracts() -> None:
    negative = command("start")
    negative["expected_state_version"] = -1
    unsupported = command("start")
    unsupported["contract_version"] = "coach_conversation_command_v2"

    with pytest.raises(ValidationError):
        ConversationCommandRequest.model_validate(negative)
    with pytest.raises(ValidationError):
        ConversationCommandRequest.model_validate(unsupported)


def test_finish_answer_requires_exactly_one_typed_or_audio_source() -> None:
    for payload in (
        {"attempt_id": "attempt_1"},
        {"attempt_id": "attempt_1", "transcript": "answer", "upload_id": "upload_1"},
    ):
        with pytest.raises(ValidationError):
            ConversationCommandRequest.model_validate(command("finish_answer", payload))


def test_end_session_payload_enforces_action_specific_ids_and_paused_draft_action() -> (
    None
):
    invalid_payloads = [
        {"unaccepted_attempt_action": "accept_attempt", "attempt_id": None},
        {"unaccepted_attempt_action": "exclude_attempt", "attempt_id": "attempt_1"},
        {"unaccepted_attempt_action": "not_applicable", "attempt_id": "attempt_1"},
        {
            "unaccepted_attempt_action": "not_applicable",
            "paused_draft_action": "submit_captured_draft",
        },
    ]

    for payload in invalid_payloads:
        with pytest.raises(ValidationError):
            ConversationCommandRequest.model_validate(command("end_session", payload))


def test_self_assessment_note_is_trimmed_and_codepoint_bounded() -> None:
    parsed = ConversationCommandRequest.model_validate(
        command(
            "record_self_assessment",
            {
                "attempt_id": "attempt_1",
                "comfort_level": "high",
                "felt_complete": False,
                "note": "  useful reflection  ",
            },
        )
    )
    assert parsed.payload.note == "useful reflection"

    with pytest.raises(ValidationError):
        ConversationCommandRequest.model_validate(
            command(
                "record_self_assessment",
                {
                    "attempt_id": "attempt_1",
                    "comfort_level": "high",
                    "felt_complete": False,
                    "note": "x" * 1001,
                },
            )
        )


def valid_live_view() -> dict:
    return {
        "session_id": "session_1",
        "experience_version": "conversational_v1",
        "status": "active",
        "conversation_state": "awaiting_next_action",
        "state_version": 12,
        "activity_version": 8,
        "retention_version": 4,
        "active_question": {
            "id": "question_1",
            "text": "Describe a difficult decision.",
            "category": "behavioural",
            "difficulty": "realistic",
            "question_kind": "planned",
            "question_state": "asked",
            "root_question_id": "question_1",
            "parent_question_id": None,
            "follow_up_depth": 0,
            "attempts_created_count": 2,
            "attempt_limit": 5,
            "attempts_remaining": 3,
        },
        "root_question": {
            "id": "question_1",
            "text": "Describe a difficult decision.",
            "category": "behavioural",
            "difficulty": "realistic",
            "question_kind": "planned",
            "question_state": "asked",
            "root_question_id": "question_1",
            "parent_question_id": None,
            "follow_up_depth": 0,
            "attempts_created_count": 2,
            "attempt_limit": 5,
            "attempts_remaining": 3,
        },
        "active_attempt": {
            "id": "attempt_1",
            "question_id": "question_1",
            "recording_type": "audio",
            "attempt_number": 2,
            "attempt_state": "completed",
            "attempt_version": 1,
            "processing_generation": 1,
            "processing_retry_count": 1,
            "processing_retry_limit": 2,
            "processing_retries_remaining": 1,
            "audio_retention_policy": "delete_after_processing",
            "audio_retention_state": "deleted",
            "transcript_version": None,
        },
        "processing": {
            "job_id": None,
            "stage": None,
            "state": "completed",
            "retryable": False,
            "retry_count": 1,
            "retry_limit": 2,
            "retries_remaining": 1,
        },
        "progress": {
            "planned_questions_total": 6,
            "planned_questions_completed": 2,
            "follow_ups_completed": 1,
            "current_planned_position": 3,
        },
        "retention": {
            "audio_policy": "delete_after_processing",
            "current_audio_state": "deleted",
        },
        "allowed_commands": ["request_coaching", "retry_answer"],
        "silence_policy": {"warning_ms": 4000, "finish_prompt_ms": 9000},
        "recoverable_error": None,
        "report_state": "not_started",
        "contract_version": "coach_live_view_v1",
    }


def test_live_view_models_the_complete_authoritative_projection() -> None:
    view = ConversationLiveView.model_validate(valid_live_view())

    assert view.root_question.id == "question_1"
    assert view.active_question.attempts_remaining == 3
    assert view.active_attempt.processing_retries_remaining == 1
    assert view.progress.current_planned_position == 3
    assert view.silence_policy.warning_ms == 4000


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("state_version",), -1),
        (("active_question", "attempts_remaining"), -1),
        (("active_attempt", "processing_retries_remaining"), -1),
        (("processing", "retry_count"), -1),
        (("silence_policy", "warning_ms"), -1),
        (("progress", "planned_questions_total"), -1),
    ],
)
def test_live_view_rejects_negative_counters(
    path: tuple[str, ...], value: object
) -> None:
    payload = valid_live_view()
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValidationError):
        ConversationLiveView.model_validate(payload)


@pytest.mark.parametrize("non_finite", [math.nan, math.inf, -math.inf])
def test_new_schema_tree_rejects_non_finite_numbers(non_finite: float) -> None:
    payload = valid_live_view()
    payload["processing"]["retry_count"] = non_finite

    with pytest.raises(ValidationError):
        ConversationLiveView.model_validate(payload)


def test_command_result_is_strict_versioned_and_uses_safe_ids() -> None:
    result = ConversationCommandResult.model_validate(
        {
            "command_id": "command_1",
            "result": "completed",
            "session_id": "session_1",
            "state": "listening",
            "state_version": 8,
            "active_question_id": "question_1",
            "active_attempt_id": "attempt_1",
            "async_job_id": None,
            "allowed_commands": ["finish_answer", "pause"],
            "contract_version": "coach_conversation_command_result_v1",
        }
    )

    assert result.state_version == 8
    with pytest.raises(ValidationError):
        ConversationCommandResult.model_validate(
            {**result.model_dump(mode="json"), "contract_version": "result_v2"}
        )


def test_core_conversational_contracts_have_stable_coach_schema_exports() -> None:
    from app.schemas import coach

    assert coach.ConversationCommandRequest is ConversationCommandRequest
    assert coach.ConversationCommandResult is ConversationCommandResult
    assert coach.ConversationLiveView is ConversationLiveView


def test_error_response_accepts_only_the_central_safe_error_registry() -> None:
    response = ConversationErrorResponse.model_validate(
        {
            "error": {
                "code": "coach_conversation_invalid_state",
                "message": "That action is not available in the current interview state.",
                "retryable": False,
                "current_state": "processing_answer",
                "current_state_version": 9,
                "correlation_id": "correlation_1",
                "details": {},
            }
        }
    )

    assert response.error.code == "coach_conversation_invalid_state"
    with pytest.raises(ValidationError):
        ConversationErrorResponse.model_validate(
            {
                "error": {
                    **response.error.model_dump(mode="json"),
                    "code": "invented_error_code",
                }
            }
        )
