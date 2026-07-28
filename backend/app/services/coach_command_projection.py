"""Persisted-context allowed-command projection shared by reads and writes."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.coach_session import InterviewSession, SessionQuestion, SessionRecording
from .coach_conversation_state import allowed_commands
from .coach_conversational_contracts import ERROR_REGISTRY


async def contextual_allowed_commands(
    db: AsyncSession, session: InterviewSession
) -> tuple[str, ...]:
    """Filter the coarse registry through V6 persisted-state predicates."""
    commands = list(allowed_commands(session))

    def remove(*names: str) -> None:
        for name in names:
            if name in commands:
                commands.remove(name)

    question = (
        await db.scalar(
            select(SessionQuestion).where(
                SessionQuestion.id == session.active_question_id,
                SessionQuestion.session_id == session.id,
            )
        )
        if session.active_question_id is not None
        else None
    )
    attempt = (
        await db.scalar(
            select(SessionRecording).where(
                SessionRecording.id == session.active_recording_id,
                SessionRecording.session_id == session.id,
            )
        )
        if session.active_recording_id is not None
        else None
    )
    session_attempt_count = int(
        await db.scalar(
            select(func.count(SessionRecording.id)).where(
                SessionRecording.session_id == session.id
            )
        )
        or 0
    )
    active_question_attempts = int(
        await db.scalar(
            select(func.count(SessionRecording.id)).where(
                SessionRecording.session_id == session.id,
                SessionRecording.question_id == session.active_question_id,
            )
        )
        or 0
    )
    terminal_attempts = int(
        await db.scalar(
            select(func.count(SessionRecording.id)).where(
                SessionRecording.session_id == session.id,
                SessionRecording.question_id == session.active_question_id,
                SessionRecording.attempt_state.in_(("completed", "unavailable")),
                SessionRecording.evaluation_state.in_(("completed", "unavailable")),
            )
        )
        or 0
    )
    transcript_target_query = select(func.count(SessionRecording.id)).where(
        SessionRecording.session_id == session.id,
        SessionRecording.current_transcript_version_id.is_not(None),
        SessionRecording.attempt_state != "deleted",
    )
    if session.status != "completed":
        transcript_target_query = transcript_target_query.where(
            SessionRecording.question_id == session.active_question_id
        )
    transcript_targets = int(await db.scalar(transcript_target_query) or 0)
    audio_targets = int(
        await db.scalar(
            select(func.count(SessionRecording.id)).where(
                SessionRecording.session_id == session.id,
                SessionRecording.recording_type == "audio",
                SessionRecording.audio_retention_state.not_in(
                    ("deleted", "not_applicable")
                ),
                SessionRecording.attempt_state.not_in(("draft", "uploaded")),
            )
        )
        or 0
    )
    if session.conversation_state == "ready" and (
        session.started_at is not None
        or session.setup_job_id is not None
        or session.setup_claim_token is not None
        or session.setup_attempt_count >= session.setup_max_attempts
        or session_attempt_count != 0
    ):
        remove("rebuild_plan")

    review_eligible = (
        question is not None
        and question.question_state == "asked"
        and question.accepted_recording_id is None
    )
    if session.conversation_state in {"awaiting_next_action", "coaching"}:
        if not review_eligible:
            remove("retry_answer", "accept_attempt")
        if (
            not review_eligible
            or question is None
            or question.attempts_created_count
            >= settings.HATCH_COACH_MAX_ATTEMPTS_PER_QUESTION
            or active_question_attempts == 0
        ):
            remove("retry_answer")
        if terminal_attempts == 0:
            remove("request_coaching", "accept_attempt")
        if transcript_targets == 0:
            remove("edit_transcript", "delete_transcript")

    if session.conversation_state == "recoverable_error":
        scope = session.recoverable_error_scope
        if session.status == "setup":
            if not (
                scope == "setup"
                and session.setup_job_id is None
                and session.setup_claim_token is None
                and session.setup_attempt_count < session.setup_max_attempts
            ):
                remove("retry_setup")
        else:
            if scope != "attempt_processing":
                remove(
                    "retry_processing",
                    "retry_answer",
                    "pause",
                    "end_session",
                )
            error = ERROR_REGISTRY.get(session.recoverable_error_code or "")
            if (
                scope != "initial_report"
                or session.report_job_id is not None
                or error is None
                or not error.retryable
            ):
                remove("retry_report")
            if not review_eligible:
                remove("retry_answer")
            if (
                attempt is None
                or attempt.attempt_state != "recoverable_error"
                or attempt.processing_retry_count >= attempt.processing_retry_limit
                or attempt.async_job_id is not None
            ):
                remove("retry_processing")

    if session.conversation_state == "paused":
        if session.resume_state not in {
            "asking",
            "listening",
            "awaiting_next_action",
            "coaching",
            "recoverable_error",
        }:
            remove("resume", "end_session")

    if session.conversation_state == "completed" and not (
        session.report_state == "failed"
        and session.report_build_reason
        in {"transcript_deletion_rebuild", "reflection_update_rebuild"}
        and session.report_job_id is None
    ):
        remove("retry_report")

    if audio_targets == 0:
        remove("delete_audio")
    if transcript_targets == 0:
        remove("delete_transcript")
    return tuple(commands)
