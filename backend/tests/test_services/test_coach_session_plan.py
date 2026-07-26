"""Contract tests for conversational session creation and plan schemas."""

from __future__ import annotations

import copy
import json
from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.models.coach_session import (
    CoachSessionEvidenceRecord,
    InterviewSession,
    InterviewSessionEvent,
    SessionQuestion,
)

from app.services.coach_session_plan import (
    EvidenceSource,
    PlannedQuestion,
    SessionPlanBuilder,
    SessionPlanError,
    claim_session_setup,
    fail_session_setup,
    finalise_session_setup,
)

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


def resolve_local_schema_ref(schema: dict, candidate: dict) -> dict:
    reference = candidate.get("$ref")
    if reference is None:
        return candidate
    return schema["$defs"][reference.rsplit("/", 1)[-1]]


def test_omitted_experience_preserves_legacy_request() -> None:
    request = CreateSessionRequest(company_name="Example", role_title="Architect")

    assert request.experience_version == "legacy_v1"
    assert request.conversational_config is None
    assert request.config.question_count == 10


def test_creation_extra_field_policy_dispatches_by_experience() -> None:
    explicit_legacy = {
        "company_name": "Example",
        "role_title": "Architect",
        "experience_version": "legacy_v1",
        "legacy_extension": {"preserved_by_legacy_client": True},
    }
    omitted_legacy = {
        "company_name": "Example",
        "role_title": "Architect",
        "legacy_extension": "accepted",
    }
    conversational = copy.deepcopy(VALID_CONVERSATIONAL_REQUEST)
    conversational["unknown_top_level"] = "must not be ignored"

    assert CreateSessionRequest.model_validate(explicit_legacy).experience_version == (
        "legacy_v1"
    )
    assert CreateSessionRequest.model_validate(omitted_legacy).experience_version == (
        "legacy_v1"
    )
    with pytest.raises(ValidationError, match="unknown_top_level"):
        CreateSessionRequest.model_validate(conversational)


def test_creation_json_schema_publishes_correlated_experience_branches() -> None:
    schema = CreateSessionRequest.model_json_schema()

    assert schema["discriminator"]["propertyName"] == "experience_version"
    assert set(schema["discriminator"]["mapping"]) == {
        "legacy_v1",
        "conversational_v1",
    }
    assert len(schema["oneOf"]) == 2
    resolved_branches = [
        resolve_local_schema_ref(schema, candidate) for candidate in schema["oneOf"]
    ]
    branches = {
        branch["properties"]["experience_version"]["const"]: branch
        for branch in resolved_branches
    }
    legacy = branches["legacy_v1"]
    conversational = branches["conversational_v1"]

    assert legacy["additionalProperties"] is True
    assert legacy["not"] == {"required": ["conversational_config"]}
    assert "experience_version" not in legacy["required"]
    assert conversational["additionalProperties"] is False
    assert {"experience_version", "conversational_config"} <= set(
        conversational["required"]
    )
    assert conversational["properties"]["conversational_config"] == {
        "$ref": "#/$defs/ConversationalConfig"
    }
    for experience_version, reference in schema["discriminator"]["mapping"].items():
        mapped_branch = resolve_local_schema_ref(schema, {"$ref": reference})
        assert (
            mapped_branch["properties"]["experience_version"]["const"]
            == experience_version
        )


def test_creation_openapi_preserves_correlated_experience_schema() -> None:
    from app.main import app

    schema = app.openapi()["components"]["schemas"]["CreateSessionRequest"]

    assert schema["discriminator"]["propertyName"] == "experience_version"
    assert len(schema["oneOf"]) == 2


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
        "2026-08-05T12:00:00-24:00",
        "2026-08-05T12:00:00+05:60",
        "2026-08-05T12:00:00-20:99",
        "2026-08-05T12:00:00+00:60",
        "2026-08-05T12:00:00+123:00",
        "2026-08-05T12:00:00-5:00",
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
        "offset-hour-out-of-range",
        "negative-offset-hour-out-of-range",
        "offset-minute-normalization",
        "negative-offset-minute-out-of-range",
        "zero-hour-offset-minute-out-of-range",
        "oversized-offset-hour",
        "single-digit-offset-hour",
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
        "2026-08-05T12:00:00+00:00",
        "2026-08-05T12:00:00-00:01",
        "2026-08-05T12:00:00+23:59",
        "2026-08-05T12:00:00-23:59",
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


@pytest.mark.parametrize(
    ("created_at", "serialized_created_at"),
    [
        ("2026-08-05T12:00:00+00:00", "2026-08-05T12:00:00Z"),
        ("2026-08-05T12:00:00+23:59", "2026-08-05T12:00:00+23:59"),
        ("2026-08-05T12:00:00-23:59", "2026-08-05T12:00:00-23:59"),
    ],
)
def test_session_plan_preserves_canonical_created_at_instant_and_offset(
    created_at: str,
    serialized_created_at: str,
) -> None:
    payload = valid_session_plan_payload()
    payload["created_at"] = created_at

    plan = ConversationalSessionPlan.model_validate(payload)
    restored = ConversationalSessionPlan.model_validate_json(plan.model_dump_json())

    assert plan.model_dump(mode="json")["created_at"] == serialized_created_at
    assert restored.created_at == plan.created_at
    assert restored.created_at.utcoffset() == plan.created_at.utcoffset()


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


def test_plan_builder_uses_duration_default_and_deterministic_mixed_distribution() -> (
    None
):
    payload = copy.deepcopy(VALID_CONVERSATIONAL_REQUEST)
    payload["conversational_config"]["planned_question_count"] = None
    payload["conversational_config"]["duration_minutes"] = 24
    request = CreateSessionRequest.model_validate(payload)
    questions = [
        PlannedQuestion(text="Behaviour example", category="Behavioural"),
        PlannedQuestion(text="System trade-off", category="Technical"),
        PlannedQuestion(text="Stakeholder scenario", category="Situational"),
        PlannedQuestion(text="Domain decision", category="Domain"),
    ]

    first = SessionPlanBuilder.build(
        request,
        sources=[],
        questions=questions,
        plan_id="plan_fixed",
        created_at="2026-08-05T12:00:00Z",
    )
    second = SessionPlanBuilder.build(
        request,
        sources=[],
        questions=list(reversed(questions)),
        plan_id="plan_fixed",
        created_at="2026-08-05T12:00:00Z",
    )

    assert first.plan.interview.planned_question_count == 4
    assert [question.category for question in first.questions] == [
        "behavioural",
        "technical",
        "situational",
        "domain",
    ]
    assert first.compatibility_key == second.compatibility_key


def test_plan_builder_normalizes_other_role_hash_and_exact_compatibility_components() -> (
    None
):
    payload = copy.deepcopy(VALID_CONVERSATIONAL_REQUEST)
    payload["conversational_config"].update(
        {
            "interview_type": "behavioural",
            "planned_question_count": 3,
            "role_family": "other",
            "role_family_label": "  Quantum\u00a0  RECRUITER  ",
        }
    )
    request = CreateSessionRequest.model_validate(payload)
    questions = [
        PlannedQuestion(text=f"Question {number}", category="culture")
        for number in range(1, 4)
    ]

    result = SessionPlanBuilder.build(
        request,
        sources=[],
        questions=questions,
        plan_id="plan_fixed",
        created_at="2026-08-05T12:00:00Z",
    )

    # SHA-256 prefix of NFKC/casefold/trim/collapsed "quantum recruiter".
    assert result.role_family_component == "other:a19da92fdf9eea05"
    assert result.compatibility_key == (
        "792b500427edc57f16d9c701272d8a00bafd8d8a1483b4fcc45e4ced51e36387"
    )


def test_plan_builder_orders_and_hashes_immutable_bounded_evidence() -> None:
    payload = copy.deepcopy(VALID_CONVERSATIONAL_REQUEST)
    payload["conversational_config"]["planned_question_count"] = 3
    payload["conversational_config"]["interview_type"] = "role_specific_verbal"
    request = CreateSessionRequest.model_validate(payload)
    sources = [
        EvidenceSource(
            evidence_id="evidence_b",
            source_type="question_bank",
            source_record_id="qb_2",
            source_record_version="2",
            source_path="question_bank/qb_2",
            snapshot_text="Second\r\nrecord",
            approval_state="reviewed_final",
        ),
        EvidenceSource(
            evidence_id="evidence_a",
            source_type="application_cv",
            source_record_id="cv_1",
            source_record_version="7",
            source_path="application/cv_1",
            snapshot_text="Cafe\u0301 delivery",
            approval_state="approved",
        ),
    ]
    questions = [
        PlannedQuestion(text=f"Question {number}", category="technical")
        for number in range(1, 4)
    ]

    result = SessionPlanBuilder.build(
        request,
        sources=sources,
        questions=questions,
        plan_id="plan_fixed",
        created_at="2026-08-05T12:00:00Z",
    )

    assert [record.evidence_id for record in result.evidence_records] == [
        "evidence_a",
        "evidence_b",
    ]
    assert result.evidence_records[0].snapshot_text == "Café delivery"
    assert result.evidence_records[1].snapshot_text == "Second\nrecord"
    assert result.plan.evidence_snapshot.package_hash.startswith("sha256:")
    assert result.plan.evidence_snapshot.package_hash == (
        "sha256:7e3d4df5f499a09778ede6bdfaa4db57219271b61520187b2e43903c8c68d07a"
    )


@pytest.mark.parametrize(
    "sources",
    [
        [
            EvidenceSource(
                evidence_id=f"record_{index}",
                source_type="master_cv",
                source_record_id=f"source_{index}",
                source_record_version="1",
                source_path=f"master/{index}",
                snapshot_text="bounded",
                approval_state="confirmed",
            )
            for index in range(31)
        ],
        [
            EvidenceSource(
                evidence_id="record",
                source_type="master_cv",
                source_record_id="source",
                source_record_version="1",
                source_path="master/record",
                snapshot_text="x" * 2001,
                approval_state="confirmed",
            )
        ],
        [
            EvidenceSource(
                evidence_id=f"record_{index}",
                source_type="master_cv",
                source_record_id=f"source_{index}",
                source_record_version="1",
                source_path=f"master/{index}",
                snapshot_text="x" * 2000,
                approval_state="confirmed",
            )
            for index in range(21)
        ],
    ],
    ids=["record-count", "record-codepoints", "package-codepoints"],
)
def test_plan_builder_rejects_evidence_above_v6_bounds(sources) -> None:
    payload = copy.deepcopy(VALID_CONVERSATIONAL_REQUEST)
    payload["conversational_config"].update(
        {"interview_type": "behavioural", "planned_question_count": 3}
    )
    request = CreateSessionRequest.model_validate(payload)

    with pytest.raises(ValueError, match="evidence"):
        SessionPlanBuilder.build(
            request,
            sources=sources,
            questions=[
                PlannedQuestion(text=f"Question {number}", category="behavioural")
                for number in range(1, 4)
            ],
            plan_id="plan_fixed",
            created_at="2026-08-05T12:00:00Z",
        )


def test_plan_builder_never_admits_draft_evidence_without_selected_consent() -> None:
    payload = copy.deepcopy(VALID_CONVERSATIONAL_REQUEST)
    payload["conversational_config"].update(
        {"interview_type": "behavioural", "planned_question_count": 3}
    )
    request = CreateSessionRequest.model_validate(payload)
    draft = EvidenceSource(
        evidence_id="draft_1",
        source_type="question_bank",
        source_record_id="question_1",
        source_record_version="1",
        source_path="question_bank/question_1",
        snapshot_text="Draft candidate example.",
        approval_state="draft",
    )

    with pytest.raises(ValueError, match="draft evidence"):
        SessionPlanBuilder.build(
            request,
            [draft],
            questions=[
                PlannedQuestion(text=f"Question {number}", category="behavioural")
                for number in range(1, 4)
            ],
            plan_id="plan_fixed",
            created_at="2026-08-05T12:00:00Z",
        )


def _conversational_request(**config_overrides) -> CreateSessionRequest:
    payload = copy.deepcopy(VALID_CONVERSATIONAL_REQUEST)
    payload["conversational_config"].update(config_overrides)
    return CreateSessionRequest.model_validate(payload)


def _three_question_build(request: CreateSessionRequest):
    return SessionPlanBuilder.build(
        request,
        sources=[
            EvidenceSource(
                evidence_id="job_context",
                source_type="job_posting",
                source_record_id="request",
                source_record_version="1",
                source_path="request/jd_text",
                snapshot_text="Design secure systems.",
                approval_state="context_only",
            )
        ],
        questions=[
            PlannedQuestion(text=f"Question {number}", category="behavioural")
            for number in range(1, 4)
        ],
        plan_id="plan_fixed",
        created_at="2026-08-05T12:00:00Z",
    )


@pytest.mark.asyncio
async def test_setup_finalises_plan_questions_and_evidence_before_ready(
    db_session,
) -> None:
    request = _conversational_request(
        interview_type="behavioural", planned_question_count=3, locale="en-GB"
    )
    session = InterviewSession(
        company_name=request.company_name,
        role_title=request.role_title,
        config={},
        status="setup",
        experience_version="conversational_v1",
    )
    db_session.add(session)
    await db_session.flush()
    session_id = session.id
    claim = await claim_session_setup(
        db_session, session_id=session.id, request=request
    )
    build = _three_question_build(request)

    assert await finalise_session_setup(db_session, claim=claim, build=build) is True
    await db_session.commit()
    db_session.expire_all()

    persisted = await db_session.get(InterviewSession, session_id)
    assert persisted is not None
    assert (persisted.status, persisted.conversation_state) == ("setup", "ready")
    assert persisted.setup_generation == persisted.setup_attempt_count == 1
    assert persisted.setup_job_id is None
    assert persisted.setup_claim_token is None
    assert persisted.session_plan_contract_version == "coach_session_plan_v1"
    assert persisted.session_plan_json["evidence_snapshot"]["package_hash"] == (
        build.plan.evidence_snapshot.package_hash
    )
    assert (
        await db_session.scalar(
            select(func.count(SessionQuestion.id)).where(
                SessionQuestion.session_id == session_id
            )
        )
        == 3
    )
    assert (
        await db_session.scalar(
            select(func.count(CoachSessionEvidenceRecord.id)).where(
                CoachSessionEvidenceRecord.session_id == session_id
            )
        )
        == 1
    )
    events = (
        (
            await db_session.execute(
                select(InterviewSessionEvent.event_type)
                .where(InterviewSessionEvent.session_id == session_id)
                .order_by(InterviewSessionEvent.sequence_number)
            )
        )
        .scalars()
        .all()
    )
    assert events == ["session_plan_started", "session_plan_completed"]


@pytest.mark.asyncio
async def test_stale_setup_worker_cannot_replace_a_new_generation(db_session) -> None:
    request = _conversational_request(
        interview_type="behavioural", planned_question_count=3, locale="en-GB"
    )
    session = InterviewSession(
        company_name=request.company_name,
        role_title=request.role_title,
        config={},
        status="setup",
        experience_version="conversational_v1",
    )
    db_session.add(session)
    await db_session.flush()
    old_claim = await claim_session_setup(
        db_session, session_id=session.id, request=request
    )
    session.setup_generation = 2
    session.setup_attempt_count = 2
    session.setup_job_id = "new_job"
    session.setup_claim_token = "new_token"
    await db_session.flush()

    assert (
        await finalise_session_setup(
            db_session, claim=old_claim, build=_three_question_build(request)
        )
        is False
    )
    assert (
        await db_session.scalar(
            select(func.count(SessionQuestion.id)).where(
                SessionQuestion.session_id == session.id
            )
        )
        == 0
    )
    assert session.session_plan_json is None


@pytest.mark.asyncio
async def test_finaliser_rejects_a_tampered_plan_snapshot_before_ready(
    db_session,
) -> None:
    request = _conversational_request(
        interview_type="behavioural", planned_question_count=3, locale="en-GB"
    )
    session = InterviewSession(
        company_name=request.company_name,
        role_title=request.role_title,
        config={},
        status="setup",
        experience_version="conversational_v1",
    )
    db_session.add(session)
    await db_session.flush()
    session_id = session.id
    claim = await claim_session_setup(
        db_session, session_id=session.id, request=request
    )
    tampered = _three_question_build(request)
    tampered.plan.compatibility.key = "0" * 64

    with pytest.raises(ValueError, match="compatibility"):
        await finalise_session_setup(db_session, claim=claim, build=tampered)

    db_session.expire_all()
    persisted = await db_session.get(InterviewSession, session_id)
    assert persisted is not None
    assert persisted.conversation_state == "planning"
    assert persisted.session_plan_json is None


@pytest.mark.asyncio
async def test_rebuild_keeps_old_audit_plan_until_matching_worker_succeeds(
    db_session,
) -> None:
    request = _conversational_request(
        interview_type="behavioural", planned_question_count=3, locale="en-GB"
    )
    session = InterviewSession(
        company_name=request.company_name,
        role_title=request.role_title,
        config={},
        status="setup",
        experience_version="conversational_v1",
        conversation_state="ready",
        setup_generation=1,
        setup_attempt_count=1,
        session_plan_json={"plan_id": "old_plan"},
        session_plan_contract_version="coach_session_plan_v1",
    )
    db_session.add(session)
    await db_session.flush()
    session_id = session.id

    claim = await claim_session_setup(
        db_session,
        session_id=session.id,
        request=request,
        rebuild=True,
    )

    assert session.conversation_state == "planning"
    assert session.session_plan_json == {"plan_id": "old_plan"}
    assert session.setup_generation == session.setup_attempt_count == 2
    assert await fail_session_setup(
        db_session,
        claim=claim,
        error_code="coach_setup_claim_expired",
        retryable=True,
    )
    db_session.expire_all()
    persisted = await db_session.get(InterviewSession, session_id)
    assert persisted is not None
    assert persisted.session_plan_json == {"plan_id": "old_plan"}
    assert (persisted.status, persisted.conversation_state) == (
        "setup",
        "recoverable_error",
    )


@pytest.mark.asyncio
async def test_setup_claim_enforces_locale_budget_expiry_and_deletion_fences(
    db_session,
) -> None:
    unsupported = _conversational_request(
        interview_type="behavioural", planned_question_count=3, locale="fr-FR"
    )
    session = InterviewSession(
        company_name=unsupported.company_name,
        role_title=unsupported.role_title,
        config={},
        status="setup",
        experience_version="conversational_v1",
    )
    db_session.add(session)
    await db_session.flush()
    with pytest.raises(SessionPlanError, match="coach_locale_unsupported"):
        await claim_session_setup(
            db_session, session_id=session.id, request=unsupported
        )

    request = _conversational_request(
        interview_type="behavioural", planned_question_count=3, locale="en-GB"
    )
    session.setup_attempt_count = session.setup_max_attempts = 3
    session.conversation_state = "recoverable_error"
    session.recoverable_error_scope = "setup"
    with pytest.raises(SessionPlanError, match="coach_setup_retry_budget_exhausted"):
        await claim_session_setup(db_session, session_id=session.id, request=request)

    session.setup_attempt_count = 0
    session.setup_generation = 0
    session.conversation_state = None
    session.recoverable_error_scope = None
    session.deletion_state = "deleting"
    with pytest.raises(SessionPlanError, match="coach_session_deletion_in_progress"):
        await claim_session_setup(db_session, session_id=session.id, request=request)


@pytest.mark.asyncio
async def test_expired_or_deleting_setup_claim_cannot_finalise_or_fail(
    db_session,
) -> None:
    request = _conversational_request(
        interview_type="behavioural", planned_question_count=3, locale="en-GB"
    )
    session = InterviewSession(
        company_name=request.company_name,
        role_title=request.role_title,
        config={},
        status="setup",
        experience_version="conversational_v1",
    )
    db_session.add(session)
    await db_session.flush()
    claimed_at = datetime(2026, 8, 5, 12)
    claim = await claim_session_setup(
        db_session,
        session_id=session.id,
        request=request,
        now=claimed_at,
        lease_seconds=60,
    )

    assert not await finalise_session_setup(
        db_session,
        claim=claim,
        build=_three_question_build(request),
        now=claimed_at + timedelta(seconds=61),
    )
    assert not await fail_session_setup(
        db_session,
        claim=claim,
        error_code="coach_setup_claim_expired",
        retryable=True,
        now=claimed_at + timedelta(seconds=61),
    )
    session.deletion_state = "deleting"
    await db_session.flush()
    assert not await finalise_session_setup(
        db_session,
        claim=claim,
        build=_three_question_build(request),
        now=claimed_at + timedelta(seconds=30),
    )
    assert session.session_plan_json is None


@pytest.mark.asyncio
async def test_exhausted_setup_failure_is_terminal_and_clears_ownership(
    db_session,
) -> None:
    request = _conversational_request(
        interview_type="behavioural", planned_question_count=3, locale="en-GB"
    )
    session = InterviewSession(
        company_name=request.company_name,
        role_title=request.role_title,
        config={},
        status="setup",
        experience_version="conversational_v1",
        setup_max_attempts=1,
    )
    db_session.add(session)
    await db_session.flush()
    claim = await claim_session_setup(
        db_session, session_id=session.id, request=request
    )

    assert await fail_session_setup(
        db_session,
        claim=claim,
        error_code="coach_contract_unsupported",
        retryable=True,
    )
    db_session.expire_all()
    persisted = await db_session.get(InterviewSession, claim.session_id)
    assert persisted is not None
    assert (persisted.status, persisted.conversation_state) == ("failed", "failed")
    assert persisted.setup_job_id is None
    assert persisted.setup_claim_token is None
    assert persisted.recoverable_error_code is None


def test_compatibility_changes_only_for_the_six_exact_v6_components() -> None:
    base = _conversational_request(
        interview_type="behavioural", planned_question_count=3, locale="en-GB"
    )
    questions = [
        PlannedQuestion(text=f"Question {number}", category="behavioural")
        for number in range(1, 4)
    ]
    base_key = SessionPlanBuilder.build(
        base,
        [],
        questions=questions,
        plan_id="base",
        created_at="2026-08-05T12:00:00Z",
    ).compatibility_key

    industry_payload = base.model_dump(mode="json")
    industry_payload["conversational_config"]["industry"] = "finance"
    industry_changed = CreateSessionRequest.model_validate(industry_payload)
    assert (
        SessionPlanBuilder.build(
            industry_changed,
            [],
            questions=questions,
            plan_id="industry",
            created_at="2026-08-05T12:00:00Z",
        ).compatibility_key
        == base_key
    )

    for field, value in (
        ("role_family", "general"),
        ("role_level", "lead"),
        ("difficulty", "challenging"),
        ("locale", "en-US"),
    ):
        payload = base.model_dump(mode="json")
        payload["conversational_config"][field] = value
        changed = CreateSessionRequest.model_validate(payload)
        assert (
            SessionPlanBuilder.build(
                changed,
                [],
                questions=questions,
                plan_id=field,
                created_at="2026-08-05T12:00:00Z",
            ).compatibility_key
            != base_key
        )
