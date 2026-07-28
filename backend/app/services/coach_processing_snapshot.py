"""Pure validation of one persisted conversational processing ownership snapshot."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from ..models.async_job import AsyncJob
from ..models.coach_session import (
    InterviewAttemptEvaluation,
    InterviewAttemptStage,
    InterviewSession,
    SessionRecording,
)


_CLAIM_KEYS = frozenset(
    {
        "processing_generation",
        "job_deadline_at",
        "source_audio_content_hash",
        "source_transcript_version_id",
        "expected_session_state_version",
        "processing_contract_version",
        "claim_token",
    }
)
TRANSCRIPT_BOUND_STAGES = frozenset(
    {
        "content_evaluation",
        "evidence_grounding",
        "follow_up_decision",
        "coaching_enrichment",
    }
)
_DEADLINE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)?$"
)


@dataclass(frozen=True)
class ProcessingSnapshot:
    claim: Mapping[str, object]
    deadline: datetime
    transcript_version_id: str | None


def _parse_claim(evaluation: InterviewAttemptEvaluation) -> ProcessingSnapshot | None:
    diagnostics = evaluation.diagnostics_json
    if not isinstance(diagnostics, Mapping):
        return None
    claim = diagnostics.get("processing_claim")
    if not isinstance(claim, Mapping) or frozenset(claim) != _CLAIM_KEYS:
        return None
    if (
        type(claim.get("processing_generation")) is not int
        or type(claim.get("expected_session_state_version")) is not int
        or not isinstance(claim.get("job_deadline_at"), str)
        or not isinstance(claim.get("processing_contract_version"), str)
        or not isinstance(claim.get("claim_token"), str)
        or not claim.get("claim_token")
        or (
            claim.get("source_audio_content_hash") is not None
            and not isinstance(claim.get("source_audio_content_hash"), str)
        )
        or (
            claim.get("source_transcript_version_id") is not None
            and not isinstance(claim.get("source_transcript_version_id"), str)
        )
    ):
        return None
    deadline_text = claim["job_deadline_at"]
    if _DEADLINE_RE.fullmatch(deadline_text) is None:
        return None
    try:
        deadline = datetime.fromisoformat(deadline_text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if deadline.tzinfo is not None:
        if deadline.utcoffset() != timezone.utc.utcoffset(deadline):
            return None
        deadline = deadline.astimezone(timezone.utc).replace(tzinfo=None)
    return ProcessingSnapshot(
        claim=claim,
        deadline=deadline,
        transcript_version_id=evaluation.transcript_version_id,
    )


def exact_processing_snapshot(
    *,
    session: InterviewSession,
    attempt: SessionRecording,
    evaluation: InterviewAttemptEvaluation,
    job: AsyncJob,
    stages: Sequence[InterviewAttemptStage],
) -> ProcessingSnapshot | None:
    """Return the exact current claim, or fail closed without inspecting content."""
    snapshot = _parse_claim(evaluation)
    if snapshot is None:
        return None
    claim = snapshot.claim
    job_id = job.id
    transcript_id = evaluation.transcript_version_id
    if (
        session.active_recording_id != attempt.id
        or attempt.session_id != session.id
        or attempt.current_evaluation_version_id != evaluation.id
        or evaluation.recording_id != attempt.id
        or evaluation.async_job_id != job_id
        or job.type != "coach_attempt_processing"
        or claim["processing_generation"] != attempt.processing_generation
        or claim["source_audio_content_hash"] != attempt.audio_content_hash
        or claim["processing_contract_version"] != "coach_processing_v1"
        or not stages
        or len({stage.stage_name for stage in stages}) != len(stages)
    ):
        return None
    if attempt.attempt_state == "pending_processing":
        if attempt.async_job_id != job_id:
            return None
    elif attempt.async_job_id is not None:
        return None
    if attempt.recording_type == "text":
        if (
            transcript_id is None
            or claim["source_transcript_version_id"] != transcript_id
            or attempt.current_transcript_version_id != transcript_id
        ):
            return None
    elif attempt.recording_type == "audio":
        if (
            claim["source_transcript_version_id"] is not None
            or attempt.current_transcript_version_id != transcript_id
        ):
            return None
    else:
        return None
    for stage in stages:
        expected_source = (
            transcript_id if stage.stage_name in TRANSCRIPT_BOUND_STAGES else None
        )
        if (
            stage.recording_id != attempt.id
            or stage.evaluation_version_id != evaluation.id
            or stage.job_id != job_id
            or stage.expected_processing_generation != attempt.processing_generation
            or stage.job_deadline_at != snapshot.deadline
            or stage.claim_token != claim["claim_token"]
            or stage.source_transcript_version_id != expected_source
        ):
            return None
    return snapshot
