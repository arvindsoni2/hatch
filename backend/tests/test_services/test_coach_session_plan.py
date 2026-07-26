"""Contract tests for conversational session creation and plan schemas."""

from __future__ import annotations

import copy
import json
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.coach import (
    AnswerEvaluation,
    CreateSessionRequest,
    RubricDimension,
    SessionFeedbackReport,
    SessionListItem,
    SessionRubric,
)
from app.schemas.coach_conversation import ConversationalSessionPlan


VALID_CONVERSATIONAL_REQUEST = {
    "company_name": " Example Ltd ",
    "role_title": " Senior Solution Architect ",
    "jd_text": " Design secure systems. ",
    "interview_date": "2026-08-05",
    "experience_version": "conversational_v1",
    "conversational_config": {
        "interview_type": "mixed",
        "difficulty": "realistic",
        "duration_minutes": 30,
        "planned_question_count": 6,
        "role_family": "solution_architecture",
        "role_level": "senior",
        "industry": "technology",
        "locale": "ZH-hant-tw",
        "focus_areas": ["stakeholder_management", "architecture"],
        "allowed_answer_modes": ["audio", "text"],
        "evidence_selection": {
            "application_cv": "approved_only",
            "master_cv": "include",
            "question_bank": "reviewed_final_only",
            "selected_question_bank_record_ids": ["question_01"],
            "company_research": "include_if_fresh",
            "draft_evidence_consent": False,
        },
        "retention": {"audio": "delete_after_processing", "transcript": "retain"},
    },
}


def test_omitted_experience_preserves_legacy_request() -> None:
    request = CreateSessionRequest(company_name="Example", role_title="Architect")

    assert request.experience_version == "legacy_v1"
    assert request.conversational_config is None
    assert request.config.question_count == 10


def test_conversational_request_normalizes_bounded_text_and_locale() -> None:
    request = CreateSessionRequest.model_validate(VALID_CONVERSATIONAL_REQUEST)

    assert request.company_name == "Example Ltd"
    assert request.role_title == "Senior Solution Architect"
    assert request.jd_text == "Design secure systems."
    assert request.conversational_config is not None
    assert request.conversational_config.locale == "zh-Hant-TW"


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("en-gb", "en-GB"),
        ("ZH-hant", "zh-Hant"),
        ("zh-HANT-tw", "zh-Hant-TW"),
        ("ES-419", "es-419"),
    ],
)
def test_locale_accepts_the_constrained_bcp47_subset(raw: str, normalized: str) -> None:
    payload = copy.deepcopy(VALID_CONVERSATIONAL_REQUEST)
    payload["conversational_config"]["locale"] = raw

    request = CreateSessionRequest.model_validate(payload)

    assert request.conversational_config.locale == normalized  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "locale",
    [
        "en-US-posix",
        "en-US-u-ca-gregory",
        "x-private",
        "en-x-private",
        "e-GB",
        "en-1234",
    ],
)
def test_locale_rejects_variants_extensions_and_private_use(locale: str) -> None:
    payload = copy.deepcopy(VALID_CONVERSATIONAL_REQUEST)
    payload["conversational_config"]["locale"] = locale

    with pytest.raises(ValidationError):
        CreateSessionRequest.model_validate(payload)


def test_conversational_request_rejects_video_answer_mode() -> None:
    payload = copy.deepcopy(VALID_CONVERSATIONAL_REQUEST)
    payload["conversational_config"]["allowed_answer_modes"] = ["video"]

    with pytest.raises(ValidationError):
        CreateSessionRequest.model_validate(payload)


def test_experience_dispatch_requires_exactly_the_matching_configuration() -> None:
    legacy_with_conversation = copy.deepcopy(VALID_CONVERSATIONAL_REQUEST)
    legacy_with_conversation["experience_version"] = "legacy_v1"
    conversational_without_config = copy.deepcopy(VALID_CONVERSATIONAL_REQUEST)
    conversational_without_config.pop("conversational_config")

    with pytest.raises(ValidationError):
        CreateSessionRequest.model_validate(legacy_with_conversation)
    with pytest.raises(ValidationError):
        CreateSessionRequest.model_validate(conversational_without_config)


def test_job_description_may_fall_back_only_to_a_linked_application() -> None:
    no_source = copy.deepcopy(VALID_CONVERSATIONAL_REQUEST)
    no_source["jd_text"] = None
    linked = copy.deepcopy(no_source)
    linked["application_id"] = "application_01"

    with pytest.raises(ValidationError):
        CreateSessionRequest.model_validate(no_source)
    assert CreateSessionRequest.model_validate(linked).jd_text is None


def test_other_role_requires_a_trimmed_label_and_registered_roles_forbid_it() -> None:
    missing = copy.deepcopy(VALID_CONVERSATIONAL_REQUEST)
    missing["conversational_config"]["role_family"] = "other"
    registered = copy.deepcopy(VALID_CONVERSATIONAL_REQUEST)
    registered["conversational_config"]["role_family_label"] = "Architect"
    valid = copy.deepcopy(missing)
    valid["conversational_config"]["role_family_label"] = "  Quantum Recruiter  "

    with pytest.raises(ValidationError):
        CreateSessionRequest.model_validate(missing)
    with pytest.raises(ValidationError):
        CreateSessionRequest.model_validate(registered)
    parsed = CreateSessionRequest.model_validate(valid)
    assert parsed.conversational_config.role_family_label == "Quantum Recruiter"  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("focus_areas", ["leadership", "leadership"]),
        (
            "focus_areas",
            [
                "leadership",
                "stakeholder_management",
                "delivery_execution",
                "problem_solving",
                "technical_depth",
                "architecture",
                "communication",
            ],
        ),
        ("allowed_answer_modes", ["audio", "audio"]),
        ("allowed_answer_modes", []),
    ],
)
def test_conversational_lists_are_unique_and_bounded(
    field: str, value: list[str]
) -> None:
    payload = copy.deepcopy(VALID_CONVERSATIONAL_REQUEST)
    payload["conversational_config"][field] = value

    with pytest.raises(ValidationError):
        CreateSessionRequest.model_validate(payload)


def test_selected_evidence_ids_are_unique_bounded_safe_tokens() -> None:
    duplicate = copy.deepcopy(VALID_CONVERSATIONAL_REQUEST)
    duplicate["conversational_config"]["evidence_selection"][
        "selected_question_bank_record_ids"
    ] = ["record_1", "record_1"]
    unsafe = copy.deepcopy(VALID_CONVERSATIONAL_REQUEST)
    unsafe["conversational_config"]["evidence_selection"][
        "selected_question_bank_record_ids"
    ] = ["../../record"]
    too_many = copy.deepcopy(VALID_CONVERSATIONAL_REQUEST)
    too_many["conversational_config"]["evidence_selection"][
        "selected_question_bank_record_ids"
    ] = [f"record_{index}" for index in range(51)]

    for payload in (duplicate, unsafe, too_many):
        with pytest.raises(ValidationError):
            CreateSessionRequest.model_validate(payload)


def test_draft_question_bank_requires_explicit_consent() -> None:
    payload = copy.deepcopy(VALID_CONVERSATIONAL_REQUEST)
    payload["conversational_config"]["evidence_selection"]["question_bank"] = (
        "include_drafts"
    )

    with pytest.raises(ValidationError, match="draft_evidence_consent"):
        CreateSessionRequest.model_validate(payload)
    payload["conversational_config"]["evidence_selection"]["draft_evidence_consent"] = (
        True
    )
    assert (
        CreateSessionRequest.model_validate(payload).conversational_config is not None
    )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("company_name",), "x" * 201),
        (("role_title",), "x" * 201),
        (("jd_text",), "x" * 100_001),
        (("interview_date",), "2026-02-30"),
        (("conversational_config", "duration_minutes"), 9),
        (("conversational_config", "duration_minutes"), 91),
        (("conversational_config", "planned_question_count"), 2),
        (("conversational_config", "planned_question_count"), 13),
    ],
    ids=[
        "company-name-overflow",
        "role-title-overflow",
        "job-description-overflow",
        "invalid-calendar-date",
        "duration-underflow",
        "duration-overflow",
        "question-count-underflow",
        "question-count-overflow",
    ],
)
def test_creation_enforces_date_codepoint_and_numeric_bounds(
    path: tuple[str, ...], value: object
) -> None:
    payload = copy.deepcopy(VALID_CONVERSATIONAL_REQUEST)
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValidationError):
        CreateSessionRequest.model_validate(payload)


def valid_session_plan_payload() -> dict:
    return {
        "plan_id": "plan_01",
        "role": {
            "title": "Senior Solution Architect",
            "role_family": "solution_architecture",
            "role_family_label": None,
            "role_level": "senior",
            "industry": "technology",
        },
        "interview": {
            "type": "mixed",
            "difficulty": "realistic",
            "duration_minutes": 30,
            "planned_question_count": 6,
            "focus_areas": ["architecture"],
            "locale": "en-GB",
            "allowed_answer_modes": ["audio", "text"],
        },
        "evidence_selection": VALID_CONVERSATIONAL_REQUEST["conversational_config"][
            "evidence_selection"
        ],
        "evidence_snapshot": {
            "package_hash": "sha256:" + "a" * 64,
            "record_count": 12,
            "contract_version": "coach_session_evidence_snapshot_v1",
        },
        "contracts": {
            "question_generation": "coach_question_generation_v2",
            "evaluation": "coach_conversational_rubric_v1",
            "delivery": "coach_delivery_policy_v1",
            "evidence_grounding": "coach_evidence_grounding_v1",
            "follow_up": "coach_follow_up_v1",
            "report": "coach_conversational_report_v1",
        },
        "retention": {"audio": "delete_after_processing", "transcript": "retain"},
        "compatibility": {
            "key": "compatibility_01",
            "version": "coach_progress_compatibility_v1",
        },
        "created_at": "2026-08-05T12:00:00Z",
    }


def test_session_plan_exposes_source_selection_retention_and_contracts() -> None:
    plan = ConversationalSessionPlan.model_validate(valid_session_plan_payload())

    assert plan.contracts.delivery == "coach_delivery_policy_v1"
    assert plan.evidence_snapshot.record_count == 12
    with pytest.raises(ValidationError):
        ConversationalSessionPlan.model_validate(
            {**plan.model_dump(mode="json"), "unknown": "not allowed"}
        )


def test_session_plan_accepts_created_at_from_loaded_json_and_direct_json() -> None:
    serialized = json.dumps(valid_session_plan_payload())

    loaded = ConversationalSessionPlan.model_validate(json.loads(serialized))
    direct = ConversationalSessionPlan.model_validate_json(serialized)

    assert loaded.created_at == datetime(2026, 8, 5, 12, tzinfo=timezone.utc)
    assert direct.created_at == loaded.created_at


def test_session_plan_json_dump_round_trips_created_at() -> None:
    original = ConversationalSessionPlan.model_validate(valid_session_plan_payload())
    dumped = original.model_dump(mode="json")
    serialized = original.model_dump_json()
    restored_from_dump = ConversationalSessionPlan.model_validate(dumped)
    restored = ConversationalSessionPlan.model_validate_json(serialized)

    assert restored_from_dump == original
    assert restored == original
    assert dumped["created_at"] == "2026-08-05T12:00:00Z"
    assert json.loads(serialized)["created_at"] == "2026-08-05T12:00:00Z"


@pytest.mark.parametrize(
    "created_at",
    [
        "not-a-datetime",
        "2026-08-05",
        "2026-08-05 12:00:00Z",
        "20260805T120000Z",
        "2026-08-05T12:00:00z",
        "2026-08-05T12:00:00.1234567Z",
        "2026-02-30T12:00:00Z",
        "2026-08-05T12:00:00+24:00",
        "2026-08-05T12:00:00-00:00",
        1_786_000_000,
        1_786_000_000.0,
        True,
        date(2026, 8, 5),
        datetime(2026, 8, 5, 12),
    ],
    ids=[
        "malformed",
        "date-only-string",
        "space-separator",
        "basic-iso",
        "lowercase-zone",
        "excess-fraction",
        "invalid-calendar-date-time",
        "invalid-zone-offset",
        "unknown-local-offset",
        "integer-timestamp",
        "float-timestamp",
        "boolean",
        "date-object",
        "naive-datetime",
    ],
)
def test_session_plan_rejects_noncanonical_or_non_datetime_created_at(
    created_at: object,
) -> None:
    payload = valid_session_plan_payload()
    payload["created_at"] = created_at

    with pytest.raises(ValidationError):
        ConversationalSessionPlan.model_validate(payload)


@pytest.mark.parametrize(
    "created_at",
    [
        "2026-08-05T12:00:00Z",
        "2026-08-05T12:00:00.123456Z",
        "2026-08-05T17:30:00+05:30",
    ],
)
def test_session_plan_accepts_canonical_timezone_aware_created_at(
    created_at: str,
) -> None:
    payload = valid_session_plan_payload()
    payload["created_at"] = created_at

    parsed = ConversationalSessionPlan.model_validate(payload)

    assert parsed.created_at.tzinfo is not None
    assert parsed.created_at.utcoffset() is not None


def test_legacy_numeric_evaluation_and_report_fixtures_keep_their_meaning() -> None:
    dimension = RubricDimension(score=7, score_band="good")
    rubric = SessionRubric(dimensions={"relevance": dimension})
    evaluation = AnswerEvaluation(scores={"relevance": 7}, overall=7.0, rubric=rubric)
    report = SessionFeedbackReport(
        session_id="legacy-session",
        overall_score=7.0,
        category_scores={"Technical": 7.0},
    )

    assert evaluation.model_dump()["scores"] == {"relevance": 7}
    assert evaluation.model_dump()["overall"] == 7.0
    assert evaluation.model_dump()["rubric"]["dimensions"]["relevance"]["score"] == 7
    assert report.model_dump()["category_scores"] == {"Technical": 7.0}


def test_session_list_additions_remain_optional_for_legacy_rows() -> None:
    item = SessionListItem.model_validate(
        {
            "id": "legacy-session",
            "company_name": "Example",
            "role_title": "Architect",
            "status": "completed",
            "created_at": "2026-08-05T12:00:00Z",
        }
    )

    assert item.experience_version is None
    assert item.conversation_state is None
    assert item.session_level is None
    assert item.retention_summary is None
