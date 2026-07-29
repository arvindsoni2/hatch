"""Locked PR2/PR3 imports and call signatures supplied by PR1."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import datetime
from inspect import signature

import pytest

from app.repositories.conversational_session_repository import (
    AttemptProcessingClaim,
    ConversationalSessionRepository,
    FollowUpAdmissionClaim,
    FollowUpCreationResult,
)
from app.services.coach_conversation_commands import (
    CoachConversationCommandService,
    ConversationCommandService,
)


def test_locked_processing_claim_is_the_eight_field_frozen_record() -> None:
    """Adding private worker fences to the public record breaks PR2 consumers."""
    assert [field.name for field in fields(AttemptProcessingClaim)] == [
        "session_id",
        "question_id",
        "recording_id",
        "transcript_version_id",
        "evaluation_version_id",
        "processing_generation",
        "job_id",
        "deadline_at",
    ]
    claim = AttemptProcessingClaim(
        session_id="session-contract",
        question_id="question-contract",
        recording_id="attempt-contract",
        transcript_version_id=None,
        evaluation_version_id="evaluation-contract",
        processing_generation=1,
        job_id="job-contract",
        deadline_at=datetime(2026, 7, 29, 12, 0),
    )
    with pytest.raises(FrozenInstanceError):
        claim.job_id = "replacement"  # type: ignore[misc]


def test_locked_repository_signatures_and_follow_up_records_are_importable() -> None:
    """Requiring an extra keyword or omitting a primitive blocks later PRs."""
    claim_signature = signature(
        ConversationalSessionRepository.claim_attempt_processing
    )
    assert tuple(claim_signature.parameters) == (
        "self",
        "recording_id",
        "expected_generation",
        "job_id",
        "deadline",
    )
    assert all(
        parameter.kind.name == "KEYWORD_ONLY"
        for name, parameter in claim_signature.parameters.items()
        if name != "self"
    )

    evaluation_signature = signature(
        ConversationalSessionRepository.create_evaluation_version
    )
    assert tuple(evaluation_signature.parameters) == (
        "self",
        "recording_id",
        "transcript_version_id",
        "evaluation_version",
        "processing_generation",
        "contract_version",
        "state",
        "async_job_id",
    )
    assert evaluation_signature.parameters["async_job_id"].default is None

    follow_up_signature = signature(
        ConversationalSessionRepository.create_follow_up_question
    )
    assert tuple(follow_up_signature.parameters) == ("self", "claim")
    assert fields(FollowUpAdmissionClaim)
    assert [field.name for field in fields(FollowUpCreationResult)] == [
        "created",
        "question_id",
        "state_version",
    ]


def test_command_service_compatibility_alias_is_exact() -> None:
    """A subclass or missing re-export is not the locked compatibility alias."""
    assert CoachConversationCommandService is ConversationCommandService
