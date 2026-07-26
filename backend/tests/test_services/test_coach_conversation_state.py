from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import settings
from app.services.coach_conversation_state import (
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


def test_allowed_commands_are_derived_from_transition_registry() -> None:
    assert allowed_commands(state="ready", status="setup") == (
        "start",
        "rebuild_plan",
        "update_retention",
    )
    assert allowed_commands(state="processing_answer", status="active") == ()
    assert "begin_answer" in allowed_commands(state="asking", status="active")


def test_require_transition_rejects_a_command_outside_its_registered_state() -> None:
    with pytest.raises(ValueError, match="coach_conversation_invalid_state"):
        require_transition(state="ready", status="setup", command_type="begin_answer")


def test_error_registry_is_complete_and_rejects_forbidden_alias() -> None:
    assert ERROR_REGISTRY["coach_conversation_version_conflict"].http_status == 409
    assert "coach_progress_incompatible_session" in ERROR_REGISTRY
    assert "coach_session_incompatible_for_progress" not in ERROR_REGISTRY
    assert all(
        item.message and isinstance(item.retryable, bool)
        for item in ERROR_REGISTRY.values()
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


def test_conversational_defaults_are_disabled_and_bounded() -> None:
    assert settings.HATCH_COACH_CONVERSATIONAL_ENABLED is False
    assert settings.HATCH_COACH_MAX_ATTEMPTS_PER_QUESTION == 5
    assert settings.HATCH_COACH_MAX_PROCESSING_RETRIES_PER_ATTEMPT == 2


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
