"""Boundary tests for the conversational command and live-view schemas."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from itertools import product

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
    ConversationalQuestionRead,
    DeleteAudioPayload,
    DeleteTranscriptPayload,
    EditTranscriptPayload,
    EndSessionPayload,
    FinishAnswerPayload,
    KeepSpeakingPayload,
    PausePayload,
    PlanInterview,
    PlanRole,
    RebuildPlanPayload,
    RecordSelfAssessmentPayload,
    RequestCoachingPayload,
    RequestHintPayload,
    ResumePayload,
    RetryAnswerPayload,
    RetryProcessingPayload,
    RetryReportPayload,
    RetrySetupPayload,
    RecoverableErrorProjection,
    ReturnToReviewPayload,
    SkipQuestionPayload,
    StartPayload,
    TranscriptVersionRead,
    UpdateRetentionPayload,
)
from app.services.coach_conversational_contracts import ERROR_REGISTRY


COMMAND_CONTRACT = "coach_conversation_command_v1"


def resolve_local_schema_ref(schema: dict, candidate: dict) -> dict:
    reference = candidate.get("$ref")
    if reference is None:
        return candidate
    return schema["$defs"][reference.rsplit("/", 1)[-1]]


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


def test_command_wrapper_preserves_constructor_dump_and_hash_input_semantics() -> None:
    payload = command("retry_answer", {"question_id": None})

    validated = ConversationCommandRequest.model_validate(payload)
    constructed = ConversationCommandRequest(**payload)
    canonical_options = {
        "mode": "json",
        "exclude_unset": False,
        "exclude_none": False,
    }

    assert validated.command_type == "retry_answer"
    assert constructed.payload.question_id is None
    assert validated.model_dump(**canonical_options) == constructed.model_dump(
        **canonical_options
    )


def test_command_envelope_forbids_extra_fields_and_mismatched_payloads() -> None:
    with pytest.raises(ValidationError):
        ConversationCommandRequest.model_validate({**command("start"), "unknown": True})
    with pytest.raises(ValidationError):
        ConversationCommandRequest.model_validate(
            command("accept_attempt", {"hint_type": "star_structure"})
        )


def test_command_json_schema_discriminates_all_envelope_branches() -> None:
    schema = ConversationCommandRequest.model_json_schema()
    discriminator = schema["discriminator"]

    assert discriminator["propertyName"] == "command_type"
    assert set(discriminator["mapping"]) == {
        command_type for command_type, _, _ in COMMAND_CASES
    }
    assert len(schema["oneOf"]) == 23

    resolved_branches = [
        resolve_local_schema_ref(schema, candidate) for candidate in schema["oneOf"]
    ]
    branches = {
        branch["properties"]["command_type"]["const"]: branch
        for branch in resolved_branches
    }
    for command_type, _, payload_type in COMMAND_CASES:
        branch = branches[command_type]
        mapped_branch = resolve_local_schema_ref(
            schema, {"$ref": discriminator["mapping"][command_type]}
        )
        assert mapped_branch == branch
        assert branch["additionalProperties"] is False
        assert set(branch["required"]) == {
            "command_id",
            "command_type",
            "expected_state_version",
            "payload",
            "contract_version",
        }
        assert branch["properties"]["payload"] == {
            "$ref": f"#/$defs/{payload_type.__name__}"
        }


def test_command_openapi_preserves_envelope_discriminator() -> None:
    from fastapi import FastAPI

    test_app = FastAPI()

    @test_app.post("/commands")
    async def submit_command(
        request: ConversationCommandRequest,
    ) -> ConversationCommandRequest:
        return request

    schema = test_app.openapi()["components"]["schemas"]["ConversationCommandRequest"]

    assert schema["discriminator"]["propertyName"] == "command_type"
    assert len(schema["discriminator"]["mapping"]) == 23
    assert all(
        reference.startswith("#/components/schemas/")
        for reference in schema["discriminator"]["mapping"].values()
    )
    assert len(schema["oneOf"]) == 23


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
            "root_question_id": None,
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
            "root_question_id": None,
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


@pytest.mark.parametrize(
    "details",
    [
        {"traceback": "Traceback: /srv/app/secrets.py"},
        {"path": "/home/user/private.env"},
        {"secret": "token-value"},
        {"message": "x" * 100_000},
        {f"key_{index}": index for index in range(100)},
        {"nested": {"authorization": "Bearer secret"}},
    ],
    ids=["stack", "path", "secret", "unbounded-string", "large-map", "nested"],
)
def test_public_error_details_reject_all_content(details: dict) -> None:
    error = {
        "code": "coach_conversation_invalid_state",
        "correlation_id": "correlation_1",
        "details": details,
    }

    with pytest.raises(ValidationError):
        ConversationErrorResponse.model_validate({"error": error})
    with pytest.raises(ValidationError):
        RecoverableErrorProjection.model_validate(
            {
                "code": "coach_conversation_invalid_state",
                "scope": "attempt_processing",
                "details": details,
            }
        )


def test_public_error_details_schema_is_content_free_and_bounded() -> None:
    schema = ConversationErrorResponse.model_json_schema()
    details_schema = schema["$defs"]["EmptyErrorDetails"]

    assert details_schema["additionalProperties"] is False
    assert details_schema["maxProperties"] == 0
    assert details_schema["properties"] == {}


@pytest.mark.parametrize("coerced", ["1", 1.0, True])
def test_new_contracts_reject_scalar_coercion_across_boundaries(
    coerced: object,
) -> None:
    command_payload = command("start")
    command_payload["expected_state_version"] = coerced
    live_payload = valid_live_view()
    live_payload["state_version"] = coerced

    with pytest.raises(ValidationError):
        ConversationCommandRequest.model_validate(command_payload)
    with pytest.raises(ValidationError):
        ConversationLiveView.model_validate(live_payload)


@pytest.mark.parametrize("coerced", ["true", "yes", 1])
def test_draft_consent_rejects_truthy_non_booleans(coerced: object) -> None:
    from tests.test_services.test_coach_session_plan import (
        VALID_CONVERSATIONAL_REQUEST,
    )

    payload = json.loads(json.dumps(VALID_CONVERSATIONAL_REQUEST))
    payload["conversational_config"]["evidence_selection"]["draft_evidence_consent"] = (
        coerced
    )

    from app.schemas.coach import CreateSessionRequest

    with pytest.raises(ValidationError):
        CreateSessionRequest.model_validate(payload)


def test_strict_contract_still_accepts_native_json_arrays_objects_and_literals() -> (
    None
):
    parsed = ConversationCommandRequest.model_validate_json(
        json.dumps(command("rebuild_plan", {"refresh_sources": True}))
    )

    assert parsed.command_type == "rebuild_plan"
    assert parsed.payload.refresh_sources is True


@pytest.mark.parametrize("model_name", ["attempt", "processing"])
def test_retry_projection_rejects_consumed_count_above_snapshot_limit(
    model_name: str,
) -> None:
    payload = valid_live_view()
    if model_name == "attempt":
        payload["active_attempt"]["processing_retry_count"] = 3
        payload["active_attempt"]["processing_retry_limit"] = 2
        payload["active_attempt"]["processing_retries_remaining"] = 0
    else:
        payload["processing"]["retry_count"] = 3
        payload["processing"]["retry_limit"] = 2
        payload["processing"]["retries_remaining"] = 0

    with pytest.raises(ValidationError):
        ConversationLiveView.model_validate(payload)


def test_question_read_enforces_planned_and_adaptive_shape_invariants() -> None:
    planned = valid_live_view()["active_question"]
    assert ConversationalQuestionRead.model_validate(planned).question_kind == "planned"

    invalid_planned = {**planned, "parent_question_id": "question_parent"}
    invalid_follow_up = {
        **planned,
        "id": "question_followup",
        "question_kind": "adaptive_follow_up",
        "root_question_id": None,
        "parent_question_id": "question_parent",
        "follow_up_depth": 1,
        "follow_up_reason": "clarify_example",
    }
    valid_follow_up = {
        **invalid_follow_up,
        "root_question_id": "question_root",
    }

    with pytest.raises(ValidationError):
        ConversationalQuestionRead.model_validate(invalid_planned)
    with pytest.raises(ValidationError):
        ConversationalQuestionRead.model_validate(invalid_follow_up)
    assert (
        ConversationalQuestionRead.model_validate(valid_follow_up).follow_up_depth == 1
    )


@pytest.mark.parametrize(
    ("source", "created_by", "edit_reason", "valid"),
    [
        ("transcription", "system", None, True),
        ("recovered_transcription", "system", None, True),
        ("candidate_text", "candidate", None, True),
        ("candidate_edit", "candidate", "transcription_error", True),
        ("transcription", "candidate", None, False),
        ("candidate_text", "system", None, False),
        ("candidate_edit", "candidate", None, False),
        ("candidate_edit", "candidate", "other", False),
    ],
)
def test_transcript_read_enforces_source_actor_and_edit_reason_combinations(
    source: str, created_by: str, edit_reason: str | None, valid: bool
) -> None:
    payload = {
        "id": "transcript_1",
        "version_number": 1,
        "transcript": "Canonical answer",
        "source": source,
        "edit_reason": edit_reason,
        "created_by": created_by,
        "processing_generation": 1,
        "created_at": datetime(2026, 8, 5, tzinfo=timezone.utc),
    }

    if valid:
        assert (
            TranscriptVersionRead.model_validate(payload).transcript
            == "Canonical answer"
        )
    else:
        with pytest.raises(ValidationError):
            TranscriptVersionRead.model_validate(payload)


@pytest.mark.parametrize(
    "transcript",
    [None, "", "  ", "line one\r\nline two", "x" * 30_001],
    ids=["missing", "empty", "whitespace", "noncanonical-newline", "overflow"],
)
def test_transcript_read_rejects_missing_empty_noncanonical_or_oversized_text(
    transcript: str | None,
) -> None:
    payload = {
        "id": "transcript_1",
        "version_number": 1,
        "transcript": transcript,
        "source": "candidate_text",
        "edit_reason": None,
        "created_by": "candidate",
        "processing_generation": 1,
        "created_at": datetime(2026, 8, 5, tzinfo=timezone.utc),
    }

    with pytest.raises(ValidationError):
        TranscriptVersionRead.model_validate(payload)


def test_persisted_plan_role_and_interview_enforce_cross_field_invariants() -> None:
    common_role = {
        "title": "Architect",
        "role_family": "solution_architecture",
        "role_family_label": None,
        "role_level": "senior",
        "industry": "technology",
    }
    with pytest.raises(ValidationError):
        PlanRole.model_validate({**common_role, "role_family_label": "Custom role"})
    with pytest.raises(ValidationError):
        PlanRole.model_validate(
            {**common_role, "role_family": "other", "role_family_label": None}
        )
    assert (
        PlanRole.model_validate(
            {**common_role, "role_family": "other", "role_family_label": "Custom role"}
        ).role_family
        == "other"
    )

    interview = {
        "type": "mixed",
        "difficulty": "realistic",
        "duration_minutes": 30,
        "planned_question_count": 6,
        "focus_areas": ["architecture"],
        "locale": "en-GB",
        "allowed_answer_modes": ["audio", "text"],
    }
    with pytest.raises(ValidationError):
        PlanInterview.model_validate(
            {**interview, "focus_areas": ["architecture", "architecture"]}
        )
    with pytest.raises(ValidationError):
        PlanInterview.model_validate(
            {**interview, "allowed_answer_modes": ["audio", "audio"]}
        )
    with pytest.raises(ValidationError):
        PlanInterview.model_validate({**interview, "locale": "EN-gb"})


@pytest.mark.parametrize(
    ("status", "state"),
    [
        ("setup", "planning"),
        ("setup", "ready"),
        ("active", "asking"),
        ("active", "processing_answer"),
        ("active", "reporting"),
        ("completed", "completed"),
        ("abandoned", "abandoned"),
        ("failed", "failed"),
    ],
)
def test_live_view_accepts_valid_status_state_pairs(status: str, state: str) -> None:
    payload = valid_live_view()
    payload.update(status=status, conversation_state=state)

    assert ConversationLiveView.model_validate(payload).conversation_state == state


@pytest.mark.parametrize(
    ("status", "state"),
    [
        ("setup", "asking"),
        ("active", "ready"),
        ("completed", "reporting"),
        ("abandoned", "completed"),
        ("failed", "recoverable_error"),
    ],
)
def test_live_view_rejects_contradictory_status_state_pairs(
    status: str, state: str
) -> None:
    payload = valid_live_view()
    payload.update(status=status, conversation_state=state)

    with pytest.raises(ValidationError):
        ConversationLiveView.model_validate(payload)


VALID_STATUS_STATE_PAIRS = {
    ("setup", "planning"),
    ("setup", "ready"),
    ("setup", "recoverable_error"),
    ("active", "asking"),
    ("active", "listening"),
    ("active", "processing_answer"),
    ("active", "awaiting_next_action"),
    ("active", "coaching"),
    ("active", "asking_follow_up"),
    ("active", "advancing"),
    ("active", "paused"),
    ("active", "reporting"),
    ("active", "recoverable_error"),
    ("completed", "completed"),
    ("abandoned", "abandoned"),
    ("failed", "failed"),
}
ALL_STATUSES = ("setup", "active", "completed", "abandoned", "failed")
ALL_STATES = (
    "planning",
    "ready",
    "asking",
    "listening",
    "processing_answer",
    "awaiting_next_action",
    "coaching",
    "asking_follow_up",
    "advancing",
    "paused",
    "reporting",
    "completed",
    "recoverable_error",
    "abandoned",
    "failed",
)


@pytest.mark.parametrize(("status", "state"), product(ALL_STATUSES, ALL_STATES))
def test_live_view_status_state_matrix_is_exhaustive(status: str, state: str) -> None:
    payload = valid_live_view()
    payload.update(status=status, conversation_state=state)

    if (status, state) in VALID_STATUS_STATE_PAIRS:
        assert ConversationLiveView.model_validate(payload).conversation_state == state
    else:
        with pytest.raises(ValidationError):
            ConversationLiveView.model_validate(payload)


def test_command_result_rejects_unknown_state_and_duplicate_allowed_commands() -> None:
    result = {
        "command_id": "command_1",
        "result": "completed",
        "session_id": "session_1",
        "state": "listening",
        "state_version": 8,
        "active_question_id": "question_1",
        "active_attempt_id": "attempt_1",
        "async_job_id": None,
        "allowed_commands": ["finish_answer", "finish_answer"],
        "contract_version": "coach_conversation_command_result_v1",
    }

    with pytest.raises(ValidationError):
        ConversationCommandResult.model_validate(result)
    with pytest.raises(ValidationError):
        ConversationCommandResult.model_validate(
            {**result, "state": "invented", "allowed_commands": []}
        )


@pytest.mark.parametrize("code", list(ERROR_REGISTRY))
def test_error_schemas_derive_exact_registry_message_and_retryability(
    code: str,
) -> None:
    definition = ERROR_REGISTRY[code]
    response = ConversationErrorResponse.model_validate(
        {"error": {"code": code, "correlation_id": "correlation_1"}}
    )
    projection = RecoverableErrorProjection.model_validate(
        {"code": code, "scope": "attempt_processing"}
    )

    assert (response.error.message, response.error.retryable) == (
        definition.message,
        definition.retryable,
    )
    assert (projection.message, projection.retryable) == (
        definition.message,
        definition.retryable,
    )


def test_error_schemas_reject_registry_metadata_mismatches() -> None:
    definition = ERROR_REGISTRY["coach_conversation_invalid_state"]
    for mismatch in (
        {"message": definition.message + " changed"},
        {"retryable": not definition.retryable},
    ):
        with pytest.raises(ValidationError):
            ConversationErrorResponse.model_validate(
                {
                    "error": {
                        "code": "coach_conversation_invalid_state",
                        "correlation_id": "correlation_1",
                        **mismatch,
                    }
                }
            )
        with pytest.raises(ValidationError):
            RecoverableErrorProjection.model_validate(
                {
                    "code": "coach_conversation_invalid_state",
                    "scope": "attempt_processing",
                    **mismatch,
                }
            )
