"""Stable public contracts for the Phase 1 conversational Coach experience."""

from __future__ import annotations

from dataclasses import dataclass

CONVERSATION_COMMAND_CONTRACT = "coach_conversation_command_v1"
CONVERSATION_COMMAND_RESULT_CONTRACT = "coach_conversation_command_result_v1"
LIVE_VIEW_CONTRACT = "coach_live_view_v1"
SESSION_PLAN_CONTRACT = "coach_session_plan_v1"
RUBRIC_CONTRACT = "coach_conversational_rubric_v1"
EVIDENCE_GROUNDING_CONTRACT = "coach_evidence_grounding_v1"
FOLLOW_UP_CONTRACT = "coach_follow_up_v1"
REPORT_CONTRACT = "coach_conversational_report_v1"
PROGRESS_CONTRACT = "coach_conversational_progress_v2"
DELIVERY_POLICY = "coach_delivery_policy_v1"


@dataclass(frozen=True)
class ErrorDefinition:
    """Frontend-safe metadata for one stable conversational error code."""

    http_status: int
    retryable: bool
    message: str


def _conflict(message: str, *, retryable: bool = False) -> ErrorDefinition:
    return ErrorDefinition(409, retryable, message)


def _unprocessable(message: str) -> ErrorDefinition:
    return ErrorDefinition(422, False, message)


def _unavailable(message: str) -> ErrorDefinition:
    return ErrorDefinition(503, True, message)


# This is the sole registry for the error codes specified by V6 Section 31.7.
# Messages deliberately contain no provider, prompt, path, or candidate content.
ERROR_REGISTRY: dict[str, ErrorDefinition] = {
    "coach_conversation_not_enabled": ErrorDefinition(
        403, False, "Conversational interview sessions are not enabled."
    ),
    "coach_conversational_command_required": _unprocessable(
        "Use the conversational command endpoint for this session."
    ),
    "coach_conversation_invalid_state": _conflict(
        "That action is not available in the current interview state."
    ),
    "coach_conversation_version_conflict": _conflict(
        "The interview changed since this view was loaded."
    ),
    "coach_command_idempotency_conflict": _conflict(
        "This command identifier was already used for a different request."
    ),
    "coach_contract_unsupported": ErrorDefinition(
        400, False, "The requested conversational contract is not supported."
    ),
    "coach_setup_claim_expired": _conflict(
        "Interview setup timed out. Retry setup to continue.", retryable=True
    ),
    "coach_setup_retry_budget_exhausted": _conflict(
        "The interview setup retry limit has been reached."
    ),
    "coach_plan_rebuild_not_allowed": _conflict(
        "The interview plan cannot be rebuilt in the current state."
    ),
    "coach_attempt_not_active": _conflict("The selected answer attempt is not active."),
    "coach_attempt_client_id_conflict": _conflict(
        "This answer identifier was already used for a different attempt."
    ),
    "coach_attempt_already_accepted": _conflict(
        "An answer has already been accepted for this question."
    ),
    "coach_attempt_limit_exhausted": _conflict(
        "The answer attempt limit has been reached."
    ),
    "coach_attempt_upload_required": _conflict(
        "Upload the captured answer before finishing it."
    ),
    "coach_attempt_upload_conflict": _conflict(
        "The answer upload conflicts with the current attempt."
    ),
    "coach_attempt_upload_missing": ErrorDefinition(
        404, False, "The answer upload could not be found."
    ),
    "coach_attempt_upload_hash_mismatch": _unprocessable(
        "The answer upload did not match its declared content hash."
    ),
    "coach_audio_upload_idempotency_conflict": _conflict(
        "This upload identifier was already used for different audio."
    ),
    "coach_attempt_retry_budget_exhausted": _conflict(
        "The processing retry limit has been reached."
    ),
    "coach_attempt_retry_source_unavailable": _conflict(
        "The source needed to retry this answer is unavailable."
    ),
    "coach_attempt_job_budget_exhausted": _conflict(
        "The answer processing deadline was reached."
    ),
    "coach_attempt_stale_claim": _conflict(
        "This answer processing claim is no longer current."
    ),
    "coach_transcript_deleted": _conflict("This transcript has been deleted."),
    "coach_transcript_version_conflict": _conflict(
        "The transcript changed since this view was loaded."
    ),
    "coach_transcript_schema_invalid": _unprocessable(
        "The transcript does not match the supported format."
    ),
    "coach_evaluation_unavailable": _unavailable(
        "The answer evaluation is temporarily unavailable."
    ),
    "coach_evaluation_evidence_span_invalid": _unprocessable(
        "The evaluation contains an invalid transcript evidence span."
    ),
    "coach_evaluation_prohibited_inference": _unprocessable(
        "The evaluation contains a prohibited inference."
    ),
    "coach_grounding_evidence_id_invalid": _unprocessable(
        "The evaluation references unknown evidence."
    ),
    "coach_grounding_source_unavailable": _unavailable(
        "The selected evidence source is unavailable."
    ),
    "coach_draft_evidence_consent_required": _unprocessable(
        "Consent is required before draft evidence can be used."
    ),
    "coach_followup_budget_exhausted": _conflict(
        "The follow-up question limit has been reached."
    ),
    "coach_followup_reason_invalid": _unprocessable(
        "The follow-up reason is not supported."
    ),
    "coach_followup_transcript_ungrounded": _unprocessable(
        "The follow-up question is not grounded in the transcript."
    ),
    "coach_followup_duplicate": _conflict(
        "That follow-up question has already been asked."
    ),
    "coach_audio_already_deleted": _conflict("This answer audio is already deleted."),
    "coach_audio_cleanup_failed": _unavailable(
        "The answer audio could not be cleaned up."
    ),
    "coach_audio_deletion_failed": _unavailable(
        "The answer audio could not be deleted."
    ),
    "coach_export_source_changed": _conflict(
        "The report changed while the export was being built.", retryable=True
    ),
    "coach_report_unavailable": _conflict("The conversational report is unavailable."),
    "coach_report_not_ready": _conflict("The conversational report is not ready."),
    "coach_report_invalidated": _conflict(
        "The conversational report is being rebuilt."
    ),
    "coach_report_conversational_snapshot_stale": _conflict(
        "The report snapshot is no longer current.", retryable=True
    ),
    "coach_conversational_session_retry_unsupported": _conflict(
        "Create another session instead of retrying this interview."
    ),
    "coach_progress_selector_conflict": ErrorDefinition(
        400, False, "Choose either an exact progress key or broad progress filters."
    ),
    "coach_progress_incompatible_session": _conflict(
        "This session is not compatible with the selected progress group."
    ),
    "coach_locale_unsupported": _unprocessable(
        "The selected locale is not supported for conversational interviews."
    ),
    "coach_session_deletion_in_progress": _conflict("This interview is being deleted."),
    "coach_session_deletion_failed": _unavailable(
        "This interview could not be deleted."
    ),
    "coach_deletion_claim_expired": _conflict(
        "The interview deletion claim expired.", retryable=True
    ),
}
