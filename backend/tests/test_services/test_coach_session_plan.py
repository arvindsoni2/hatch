"""Contract tests for conversational session creation and plan schemas."""

from __future__ import annotations

import copy
import json
import zipfile
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.models.async_job import AsyncJob
from app.models.coach_session import (
    CompanyResearch,
    CoachSessionEvidenceRecord,
    InterviewSession,
    InterviewSessionEvent,
    SessionQuestion,
)
from app.models.application import Application
from app.models.document import GeneratedDocument
from app.models.job import JobPosting
from app.models.question_bank import QuestionBankItem

from app.services.coach_session_plan import (
    EvidenceSource,
    PlannedQuestion,
    SessionPlanBuilder,
    SessionPlanError,
    _canonical_redacted_text,
    _read_supported_cv,
    claim_session_setup,
    fail_session_setup,
    finalise_session_setup,
    load_claim_planning_request,
    load_session_plan_sources,
    persist_session_plan,
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
    payload["conversational_config"]["evidence_selection"][
        "selected_question_bank_record_ids"
    ] = []
    for field in ("application_id", "jd_text", "company_name", "role_title"):
        if field in config_overrides:
            payload[field] = config_overrides.pop(field)
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
@pytest.mark.parametrize("invalid_state", ["stale", "expired", "deleting"])
async def test_source_loading_checks_full_live_claim_before_any_external_loader(
    db_session, invalid_state: str
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
    claim = await claim_session_setup(
        db_session, session_id=session.id, request=request
    )
    if invalid_state == "stale":
        session.setup_claim_token = "replacement-token"
    elif invalid_state == "expired":
        session.setup_claim_expires_at = datetime.utcnow() - timedelta(seconds=1)
    else:
        session.deletion_state = "deleting"
    await db_session.flush()

    with (
        patch("app.services.coach_session_plan._master_cv_sources") as master_loader,
        pytest.raises(SessionPlanError, match="coach_conversation_invalid_state"),
    ):
        await load_session_plan_sources(db_session, request, claim=claim)
    master_loader.assert_not_called()


@pytest.mark.asyncio
async def test_source_loading_rechecks_claim_after_external_extraction(
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
    claim = await claim_session_setup(
        db_session, session_id=session.id, request=request
    )

    def invalidate_claim() -> list[EvidenceSource]:
        session.deletion_state = "deleting"
        return []

    with (
        patch(
            "app.services.coach_session_plan._master_cv_sources",
            side_effect=invalidate_claim,
        ) as master_loader,
        pytest.raises(SessionPlanError, match="coach_conversation_invalid_state"),
    ):
        await load_session_plan_sources(db_session, request, claim=claim)
    master_loader.assert_called_once()


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
        planning_request_json=request.model_dump(mode="json"),
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


@pytest.mark.asyncio
async def test_source_selection_uses_latest_eligible_versions_and_exact_policy(
    db_session, tmp_path: Path
) -> None:
    job = JobPosting(
        id="job_1",
        title="Architect",
        company="Example Ltd",
        description="Fallback distributed systems job description.",
        url="https://example.test/job",
        source="manual",
    )
    application = Application(
        id="application_1",
        job_id=job.id,
        status="discovered",
        priority="normal",
        cv_version=str(tmp_path / "current.txt"),
    )
    (tmp_path / "current.txt").write_text("Current unapproved CV", encoding="utf-8")
    (tmp_path / "approved-old.txt").write_text("Old approved CV", encoding="utf-8")
    (tmp_path / "approved-new.txt").write_text(
        "Latest approved platform migration CV", encoding="utf-8"
    )
    documents = [
        GeneratedDocument(
            id="approved_old",
            application_id=application.id,
            document_type="cv",
            version=1,
            file_path=str(tmp_path / "approved-old.txt"),
            status="approved",
        ),
        GeneratedDocument(
            id="approved_new",
            application_id=application.id,
            document_type="cv",
            version=2,
            file_path=str(tmp_path / "approved-new.txt"),
            status="approved",
        ),
    ]
    questions = [
        QuestionBankItem(
            id="qb_final",
            type="interview_question",
            title="Final delivery story",
            answer_draft="Delivered a resilient migration.",
            confidence="final",
            updated_at=datetime(2026, 8, 4),
        ),
        QuestionBankItem(
            id="qb_reviewed",
            type="star_story",
            title="Reviewed stakeholder story",
            answer_draft="Aligned executive stakeholders.",
            confidence="reviewed",
            updated_at=datetime(2026, 8, 5),
        ),
        QuestionBankItem(
            id="qb_draft",
            type="star_story",
            title="Draft story",
            answer_draft="Must remain excluded.",
            confidence="draft",
            updated_at=datetime(2026, 8, 6),
        ),
    ]
    research = [
        CompanyResearch(
            id="research_old",
            company_name="Example Ltd",
            description="Expired research",
            cached_at=datetime(2026, 7, 1),
            expires_at=datetime(2026, 7, 2),
        ),
        CompanyResearch(
            id="research_fresh",
            company_name="Example Ltd",
            sector="Technology",
            description="Current cloud platform strategy",
            cached_at=datetime(2026, 8, 4),
            expires_at=datetime(2026, 9, 1),
        ),
    ]
    db_session.add_all([job, application, *documents, *questions, *research])
    await db_session.commit()
    request = _conversational_request(
        application_id="application_1",
        jd_text=None,
        interview_type="mixed",
        planned_question_count=3,
        locale="en-GB",
    )
    request_payload = request.model_dump(mode="json")
    request_payload["conversational_config"]["evidence_selection"][
        "selected_question_bank_record_ids"
    ] = []
    request = CreateSessionRequest.model_validate(request_payload)
    master = {
        "personal": {"email": "private@example.test"},
        "summary": "Enterprise architecture leader",
        "experience": [{"achievements": ["Reduced migration risk"]}],
    }
    master_path = tmp_path / "master_cv.json"
    master_path.write_text(json.dumps(master), encoding="utf-8")

    with patch(
        "app.services.coach_session_plan.resolve_master_cv_path",
        return_value=master_path,
    ):
        normalized = await load_claim_planning_request(
            db_session, request=request, current_retention=None
        )
        sources = await load_session_plan_sources(
            db_session,
            normalized,
            now=datetime(2026, 8, 5, 12),
            managed_cv_roots=(tmp_path,),
        )

    assert normalized.jd_text == "Fallback distributed systems job description."
    assert [
        source.source_record_id
        for source in sources
        if source.source_type == "application_cv"
    ] == ["approved_new"]
    assert "Latest approved" in next(
        source.snapshot_text
        for source in sources
        if source.source_type == "application_cv"
    )
    assert {
        source.source_record_id
        for source in sources
        if source.source_type == "question_bank"
    } == {"qb_final", "qb_reviewed"}
    assert [
        source.source_record_id
        for source in sources
        if source.source_type == "company_research"
    ] == ["research_fresh"]
    assert all("private@example.test" not in source.snapshot_text for source in sources)


@pytest.mark.asyncio
async def test_current_application_cv_fallback_is_redacted_and_labelled_unapproved(
    db_session, tmp_path: Path
) -> None:
    current_path = tmp_path / "current.txt"
    current_path.write_text(
        "Led cloud delivery. email=person@example.test API_KEY=sk-secret-canary "
        "+44 7700 900123",
        encoding="utf-8",
    )
    application = Application(
        id="application_1",
        status="discovered",
        priority="normal",
        cv_version=str(current_path),
    )
    db_session.add(application)
    await db_session.commit()
    payload = _conversational_request(
        application_id="application_1",
        interview_type="behavioural",
        planned_question_count=3,
        locale="en-GB",
    ).model_dump(mode="json")
    payload["conversational_config"]["evidence_selection"]["application_cv"] = (
        "current_if_no_approved"
    )
    payload["conversational_config"]["evidence_selection"]["master_cv"] = "exclude"
    payload["conversational_config"]["evidence_selection"]["question_bank"] = "exclude"
    payload["conversational_config"]["evidence_selection"][
        "selected_question_bank_record_ids"
    ] = []
    request = CreateSessionRequest.model_validate(payload)

    sources = await load_session_plan_sources(
        db_session, request, managed_cv_roots=(tmp_path,)
    )
    selected = next(
        source for source in sources if source.source_type == "application_cv"
    )

    assert selected.source_record_id == application.id
    assert selected.approval_state == "candidate_selected_unapproved"
    assert len(selected.source_record_version) == 64
    assert "person@example.test" not in selected.snapshot_text
    assert "sk-secret-canary" not in selected.snapshot_text
    assert "7700 900123" not in selected.snapshot_text


@pytest.mark.asyncio
async def test_planning_request_redacts_secrets_before_claim_persistence(
    db_session,
) -> None:
    request = _conversational_request(
        interview_type="behavioural",
        planned_question_count=3,
        locale="en-GB",
        jd_text="Design secure systems. API_KEY=secret-canary",
    )
    normalized = await load_claim_planning_request(db_session, request=request)
    assert normalized.jd_text is not None
    assert "secret-canary" not in normalized.jd_text

    session = InterviewSession(
        company_name=normalized.company_name,
        role_title=normalized.role_title,
        config={},
        status="setup",
        experience_version="conversational_v1",
    )
    db_session.add(session)
    await db_session.flush()
    await claim_session_setup(
        db_session,
        session_id=session.id,
        request=normalized,
    )
    await db_session.refresh(session)
    assert "secret-canary" not in json.dumps(session.planning_request_json)


@pytest.mark.asyncio
async def test_source_loader_rejects_oversized_snapshot_without_truncation(
    db_session, tmp_path: Path
) -> None:
    current_path = tmp_path / "oversized.txt"
    current_path.write_text("x" * 2001, encoding="utf-8")
    application = Application(
        id="application_oversized",
        status="discovered",
        priority="normal",
        cv_version=str(current_path),
    )
    db_session.add(application)
    await db_session.commit()
    payload = _conversational_request(
        application_id=application.id,
        interview_type="behavioural",
        planned_question_count=3,
        locale="en-GB",
    ).model_dump(mode="json")
    selection = payload["conversational_config"]["evidence_selection"]
    selection.update(
        {
            "application_cv": "current_if_no_approved",
            "master_cv": "exclude",
            "question_bank": "exclude",
            "selected_question_bank_record_ids": [],
            "company_research": "exclude",
        }
    )

    with pytest.raises(SessionPlanError, match="coach_contract_unsupported"):
        await load_session_plan_sources(
            db_session,
            CreateSessionRequest.model_validate(payload),
            managed_cv_roots=(tmp_path,),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("layout", ["backend", "app"])
async def test_source_loader_defaults_to_the_runtime_data_root(
    db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, layout: str
) -> None:
    runtime = tmp_path / layout
    managed = runtime / "data" / "generated"
    managed.mkdir(parents=True)
    current_path = managed / "current.txt"
    current_path.write_text("Runtime-managed candidate CV", encoding="utf-8")
    monkeypatch.chdir(runtime)
    application = Application(
        id=f"application_runtime_{layout}",
        status="discovered",
        priority="normal",
        cv_version=str(current_path),
    )
    db_session.add(application)
    await db_session.commit()
    payload = _conversational_request(
        application_id=application.id,
        interview_type="behavioural",
        planned_question_count=3,
        locale="en-GB",
    ).model_dump(mode="json")
    payload["conversational_config"]["evidence_selection"].update(
        {
            "application_cv": "current_if_no_approved",
            "master_cv": "exclude",
            "question_bank": "exclude",
            "company_research": "exclude",
        }
    )

    sources = await load_session_plan_sources(
        db_session, CreateSessionRequest.model_validate(payload)
    )

    assert any(source.source_type == "application_cv" for source in sources)


@pytest.mark.asyncio
async def test_master_cv_file_is_bounded_before_loading_or_json_parsing(
    db_session, tmp_path: Path
) -> None:
    master_path = tmp_path / "master_cv.json"
    with master_path.open("wb") as output:
        output.truncate(10 * 1024 * 1024 + 1)
    request = _conversational_request(
        interview_type="behavioural", planned_question_count=3, locale="en-GB"
    )

    with (
        patch(
            "app.services.coach_session_plan.resolve_master_cv_path",
            return_value=master_path,
        ),
        patch("app.services.coach_session_plan.json.loads") as parser,
        pytest.raises(SessionPlanError, match="coach_grounding_source_unavailable"),
    ):
        await load_session_plan_sources(db_session, request)

    parser.assert_not_called()


@pytest.mark.asyncio
async def test_master_cv_subset_is_bounded_before_evidence_ledger(
    db_session, tmp_path: Path
) -> None:
    master_path = tmp_path / "master_cv.json"
    master_path.write_text(json.dumps({"summary": "x" * 40_001}), encoding="utf-8")
    request = _conversational_request(
        interview_type="behavioural", planned_question_count=3, locale="en-GB"
    )

    with (
        patch(
            "app.services.coach_session_plan.resolve_master_cv_path",
            return_value=master_path,
        ),
        patch("app.services.coach_session_plan.build_evidence_ledger") as ledger,
        pytest.raises(SessionPlanError, match="coach_contract_unsupported"),
    ):
        await load_session_plan_sources(db_session, request)

    ledger.assert_not_called()


@pytest.mark.asyncio
async def test_question_bank_snapshot_is_bounded_before_orm_materialization(
    db_session,
) -> None:
    item = QuestionBankItem(
        id="qb_oversized",
        type="star_story",
        title="Oversized story",
        answer_draft="x" * 2001,
        confidence="reviewed",
        updated_at=datetime(2026, 8, 5),
    )
    db_session.add(item)
    await db_session.commit()
    db_session.expunge_all()
    request = _conversational_request(
        interview_type="behavioural", planned_question_count=3, locale="en-GB"
    )

    with pytest.raises(SessionPlanError, match="coach_contract_unsupported"):
        await load_session_plan_sources(db_session, request)

    assert not any(
        isinstance(value, QuestionBankItem)
        for value in db_session.identity_map.values()
    )


@pytest.mark.asyncio
async def test_cv_locator_rejects_outside_managed_root_and_symlink(
    db_session, tmp_path: Path
) -> None:
    managed = tmp_path / "managed"
    managed.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("Outside candidate CV", encoding="utf-8")
    application = Application(
        id="application_path_safety",
        status="discovered",
        priority="normal",
        cv_version=str(outside),
    )
    db_session.add(application)
    await db_session.commit()
    payload = _conversational_request(
        application_id=application.id,
        interview_type="behavioural",
        planned_question_count=3,
        locale="en-GB",
    ).model_dump(mode="json")
    selection = payload["conversational_config"]["evidence_selection"]
    selection.update(
        {
            "application_cv": "current_if_no_approved",
            "master_cv": "exclude",
            "question_bank": "exclude",
            "company_research": "exclude",
        }
    )
    request = CreateSessionRequest.model_validate(payload)

    with pytest.raises(SessionPlanError, match="coach_grounding_source_unavailable"):
        await load_session_plan_sources(
            db_session, request, managed_cv_roots=(managed,)
        )

    symlink = managed / "linked.txt"
    symlink.symlink_to(outside)
    application.cv_version = str(symlink)
    await db_session.commit()
    with pytest.raises(SessionPlanError, match="coach_grounding_source_unavailable"):
        await load_session_plan_sources(
            db_session, request, managed_cv_roots=(managed,)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    ["docx_entries", "docx_uncompressed", "pdf_pages", "compressed_size", "extension"],
)
async def test_cv_extraction_rejects_archive_and_page_bombs(
    db_session, tmp_path: Path, kind: str
) -> None:
    managed = tmp_path / "managed"
    managed.mkdir()
    suffix = (
        ".docx"
        if kind.startswith("docx")
        else ".pdf"
        if kind == "pdf_pages"
        else ".rtf"
        if kind == "extension"
        else ".txt"
    )
    locator = managed / f"bomb{suffix}"
    if kind == "docx_entries":
        with zipfile.ZipFile(locator, "w") as archive:
            for index in range(513):
                archive.writestr(f"entry-{index}.xml", "x")
        expected = "coach_grounding_source_unavailable"
    elif kind == "docx_uncompressed":
        with zipfile.ZipFile(locator, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("huge.xml", b"x" * (50 * 1024 * 1024 + 1))
        expected = "coach_grounding_source_unavailable"
    elif kind == "pdf_pages":
        locator.write_bytes(b"%PDF-1.7\n%%EOF\n")
        expected = "coach_grounding_source_unavailable"
    elif kind == "compressed_size":
        with locator.open("wb") as output:
            output.truncate(10 * 1024 * 1024 + 1)
        expected = "coach_grounding_source_unavailable"
    else:
        locator.write_text("Unsupported CV", encoding="utf-8")
        expected = "coach_grounding_source_unavailable"
    application = Application(
        id=f"application_{kind}",
        status="discovered",
        priority="normal",
        cv_version=str(locator),
    )
    db_session.add(application)
    await db_session.commit()
    payload = _conversational_request(
        application_id=application.id,
        interview_type="behavioural",
        planned_question_count=3,
        locale="en-GB",
    ).model_dump(mode="json")
    selection = payload["conversational_config"]["evidence_selection"]
    selection.update(
        {
            "application_cv": "current_if_no_approved",
            "master_cv": "exclude",
            "question_bank": "exclude",
            "company_research": "exclude",
        }
    )

    with pytest.raises(SessionPlanError, match=expected):
        await load_session_plan_sources(
            db_session,
            CreateSessionRequest.model_validate(payload),
            managed_cv_roots=(managed,),
        )


def test_pdf_cv_is_rejected_without_invoking_the_parser(tmp_path: Path) -> None:
    managed = tmp_path / "managed"
    managed.mkdir()
    locator = managed / "candidate.pdf"
    locator.write_bytes(b"%PDF-1.7\n%%EOF\n")

    with (
        patch("pypdf.PdfReader") as reader,
        pytest.raises(SessionPlanError, match="coach_grounding_source_unavailable"),
    ):
        _read_supported_cv(str(locator), managed_cv_roots=(managed,))

    reader.assert_not_called()


@pytest.mark.asyncio
async def test_explicit_missing_question_bank_selection_fails_closed(
    db_session,
) -> None:
    payload = _conversational_request(
        interview_type="behavioural", planned_question_count=3, locale="en-GB"
    ).model_dump(mode="json")
    payload["conversational_config"]["evidence_selection"][
        "selected_question_bank_record_ids"
    ] = ["missing_record"]
    request = CreateSessionRequest.model_validate(payload)

    with pytest.raises(SessionPlanError, match="coach_grounding_source_unavailable"):
        await load_session_plan_sources(db_session, request)


@pytest.mark.asyncio
async def test_company_research_question_bank_note_is_context_only_regardless_confidence(
    db_session,
) -> None:
    db_session.add(
        QuestionBankItem(
            id="company_note",
            type="company_research_note",
            title="Research note",
            answer_draft="Public company context",
            confidence="draft",
            updated_at=datetime(2026, 8, 5),
        )
    )
    await db_session.commit()
    request = _conversational_request(
        interview_type="behavioural", planned_question_count=3, locale="en-GB"
    )

    sources = await load_session_plan_sources(db_session, request)
    note = next(
        source for source in sources if source.source_record_id == "company_note"
    )
    assert note.approval_state == "context_only"
    assert note.source_path == "question_bank/company_research_note"


@pytest.mark.asyncio
async def test_default_question_bank_overflow_fails_instead_of_truncating(
    db_session,
) -> None:
    db_session.add_all(
        [
            QuestionBankItem(
                id=f"question_{index:02d}",
                type="star_story",
                title=f"Story {index}",
                answer_draft="Reviewed evidence",
                confidence="reviewed",
                updated_at=datetime(2026, 8, 5),
            )
            for index in range(31)
        ]
    )
    await db_session.commit()

    with pytest.raises(SessionPlanError, match="coach_contract_unsupported"):
        await load_session_plan_sources(
            db_session,
            _conversational_request(
                interview_type="behavioural",
                planned_question_count=3,
                locale="en-GB",
            ),
        )


@pytest.mark.asyncio
async def test_company_research_uses_exact_normalized_name_in_bounded_query(
    db_session,
) -> None:
    db_session.add(
        CompanyResearch(
            id="normalized_company",
            company_name="  EXAMPLE   LTD  ",
            description="Normalized exact match",
            cached_at=datetime(2026, 8, 4),
            expires_at=datetime(2026, 9, 1),
        )
    )
    await db_session.commit()
    sources = await load_session_plan_sources(
        db_session,
        _conversational_request(
            interview_type="behavioural", planned_question_count=3, locale="en-GB"
        ),
        now=datetime(2026, 8, 5),
    )
    assert any(source.source_record_id == "normalized_company" for source in sources)


@pytest.mark.asyncio
async def test_finaliser_requires_exact_selected_question_ids_and_context_approvals(
    db_session,
) -> None:
    payload = _conversational_request(
        interview_type="behavioural", planned_question_count=3, locale="en-GB"
    ).model_dump(mode="json")
    payload["conversational_config"]["evidence_selection"][
        "selected_question_bank_record_ids"
    ] = ["question_required"]
    request = CreateSessionRequest.model_validate(payload)
    session = InterviewSession(
        company_name=request.company_name,
        role_title=request.role_title,
        config={},
        status="setup",
        experience_version="conversational_v1",
    )
    db_session.add(session)
    await db_session.flush()
    claim = await claim_session_setup(
        db_session, session_id=session.id, request=request
    )
    valid = SessionPlanBuilder.build(
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
            ),
            EvidenceSource(
                evidence_id="question_required",
                source_type="question_bank",
                source_record_id="question_required",
                source_record_version="1",
                source_path="question_bank/answer",
                snapshot_text="A reviewed answer.",
                approval_state="reviewed",
            ),
        ],
        questions=[
            PlannedQuestion(text=f"Question {number}", category="behavioural")
            for number in range(1, 4)
        ],
        plan_id="policy_tamper",
        created_at="2026-08-05T12:00:00Z",
    )
    job_record = next(
        record
        for record in valid.evidence_records
        if record.source_type == "job_posting"
    )
    build = replace(
        valid,
        evidence_records=(replace(job_record, approval_state="approved"),),
    )

    with pytest.raises(ValueError, match="evidence|question|context"):
        await finalise_session_setup(db_session, claim=claim, build=build)


@pytest.mark.asyncio
async def test_retry_uses_only_stored_request_and_rebuild_overlays_current_retention(
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
    initial = await claim_session_setup(
        db_session, session_id=session.id, request=request
    )
    assert await fail_session_setup(
        db_session,
        claim=initial,
        error_code="coach_setup_claim_expired",
        retryable=True,
    )
    replacement_payload = request.model_dump(mode="json")
    replacement_payload["role_title"] = "Attacker replacement"
    replacement = CreateSessionRequest.model_validate(replacement_payload)

    with pytest.raises(SessionPlanError, match="coach_conversation_invalid_state"):
        await claim_session_setup(
            db_session,
            session_id=session.id,
            request=replacement,
        )
    assert session.conversation_state == "recoverable_error"
    assert session.recoverable_error_scope == "setup"
    retry = await claim_session_setup(db_session, session_id=session.id)
    loaded = await load_claim_planning_request(db_session, claim=retry)
    assert loaded.role_title == request.role_title

    await fail_session_setup(
        db_session,
        claim=retry,
        error_code="coach_setup_claim_expired",
        retryable=True,
    )
    session.conversation_state = "ready"
    session.retention_policy_json = {
        "audio": "retain_until_deleted",
        "transcript": "retain",
    }
    await db_session.flush()
    rebuild = await claim_session_setup(db_session, session_id=session.id, rebuild=True)
    rebuilt_request = await load_claim_planning_request(db_session, claim=rebuild)
    assert rebuilt_request.conversational_config.retention.audio == (
        "retain_until_deleted"
    )
    assert (
        session.planning_request_json["conversational_config"]["retention"]["audio"]
        == "delete_after_processing"
    )
    build = _three_question_build(rebuilt_request)
    assert await finalise_session_setup(db_session, claim=rebuild, build=build)
    await db_session.refresh(session)
    assert session.conversation_state == "ready"
    assert session.retention_policy_json["audio"] == "retain_until_deleted"


def test_explicit_empty_questions_fail_and_default_questions_are_grounded() -> None:
    request = _conversational_request(
        interview_type="mixed",
        planned_question_count=3,
        locale="en-GB",
        focus_areas=["architecture"],
    )
    sources = [
        EvidenceSource(
            evidence_id="job_context",
            source_type="job_posting",
            source_record_id="request",
            source_record_version="1",
            source_path="planning_request/jd_text",
            snapshot_text="Design zero-trust migration platforms.",
            approval_state="context_only",
        )
    ]

    with pytest.raises(ValueError, match="planned question count"):
        SessionPlanBuilder.build(request, sources, questions=[])
    result = SessionPlanBuilder.build(
        request,
        sources,
        questions=None,
        plan_id="grounded",
        created_at="2026-08-05T12:00:00Z",
    )
    rendered = " ".join(question.text for question in result.questions).casefold()
    assert "senior solution architect" in rendered
    assert "architecture" in rendered
    assert "zero-trust" in rendered


def test_builder_canonically_redacts_direct_evidence_without_corrupting_years() -> None:
    request = _conversational_request(
        interview_type="behavioural", planned_question_count=3, locale="en-GB"
    )
    raw = """AWS_ACCESS_KEY_ID='AKIA-CANARY'
AWS_SECRET_ACCESS_KEY = "aws-secret-canary"
"client_secret": "client-canary"
password='password-canary'
api_key: "api-canary"
token = token-canary
-----BEGIN PRIVATE KEY-----\npem-canary\n-----END PRIVATE KEY-----
person@example.test +44 7700 900123 career 2018-2023"""
    source = EvidenceSource(
        evidence_id="job_context",
        source_type="job_posting",
        source_record_id="request",
        source_record_version="1",
        source_path="request/jd_text",
        snapshot_text=raw,
        approval_state="context_only",
    )
    first = SessionPlanBuilder.build(
        request,
        [source],
        questions=[
            PlannedQuestion(text=f"Question {number}", category="behavioural")
            for number in range(1, 4)
        ],
        plan_id="redacted",
        created_at="2026-08-05T12:00:00Z",
    )
    snapshot = first.evidence_records[0].snapshot_text
    for canary in (
        "AKIA-CANARY",
        "aws-secret-canary",
        "client-canary",
        "password-canary",
        "api-canary",
        "token-canary",
        "pem-canary",
        "person@example.test",
        "7700 900123",
    ):
        assert canary not in snapshot
    assert "2018-2023" in snapshot

    second = SessionPlanBuilder.build(
        request,
        [replace(source, snapshot_text=snapshot)],
        questions=first.questions,
        plan_id="redacted_again",
        created_at="2026-08-05T12:00:00Z",
    )
    assert second.evidence_records[0].snapshot_text == snapshot
    assert (
        second.evidence_records[0].content_hash
        == first.evidence_records[0].content_hash
    )


def test_default_questions_use_the_same_redacted_source_as_evidence() -> None:
    request = _conversational_request(
        interview_type="behavioural", planned_question_count=3, locale="en-GB"
    )
    source = EvidenceSource(
        evidence_id="job_context",
        source_type="job_posting",
        source_record_id="request",
        source_record_version="1",
        source_path="request/jd_text",
        snapshot_text="api_key=question-secret-canary Design secure systems.",
        approval_state="context_only",
    )

    build = SessionPlanBuilder.build(request, [source], questions=None)

    rendered = " ".join(question.text for question in build.questions)
    assert "question-secret-canary" not in rendered
    assert "question-secret-canary" not in build.evidence_records[0].snapshot_text


def test_json_redaction_is_valid_recursive_and_idempotent() -> None:
    original = json.dumps(
        {
            "token": "[REDACTED]",
            "client_secret": "json-secret-canary",
            "summary": (
                "Contact person@example.test or +44 7700 900123; career 2018-2023; "
                "api_key=leaf-secret-canary"
            ),
            "personal": {"name": "Private Person"},
        }
    )

    first = _canonical_redacted_text(original)
    parsed = json.loads(first)

    assert parsed["token"] == "[REDACTED]"
    assert parsed["client_secret"] == "[REDACTED]"
    assert parsed["personal"] == "[REDACTED]"
    assert "json-secret-canary" not in first
    assert "leaf-secret-canary" not in first
    assert "person@example.test" not in first
    assert "7700 900123" not in first
    assert "2018-2023" in first
    assert _canonical_redacted_text(first) == first


def test_builder_recursively_redacts_parseable_json_personal_and_contact_keys() -> None:
    request = _conversational_request(
        interview_type="behavioural", planned_question_count=3, locale="en-GB"
    )
    source = EvidenceSource(
        evidence_id="job_context",
        source_type="job_posting",
        source_record_id="request",
        source_record_version="1",
        source_path="request/jd_text",
        snapshot_text=json.dumps(
            {
                "summary": "Led delivery from 2018-2023",
                "personal": {"name": "Private Person", "dob": "1990-01-01"},
                "contact": {"email": "private@example.test", "phone": "+447700900123"},
                "client_secret": "json-secret-canary",
            }
        ),
        approval_state="context_only",
    )
    build = SessionPlanBuilder.build(
        request,
        [source],
        questions=[
            PlannedQuestion(text=f"Question {number}", category="behavioural")
            for number in range(1, 4)
        ],
        plan_id="json_redacted",
        created_at="2026-08-05T12:00:00Z",
    )
    snapshot = build.evidence_records[0].snapshot_text
    assert "Private Person" not in snapshot
    assert "private@example.test" not in snapshot
    assert "json-secret-canary" not in snapshot
    assert "2018-2023" in snapshot


@pytest.mark.asyncio
async def test_persistence_rejects_noncanonical_unredacted_evidence_build(
    db_session,
) -> None:
    request = _conversational_request(
        interview_type="behavioural", planned_question_count=3, locale="en-GB"
    )
    build = _three_question_build(request)
    record = build.evidence_records[0]
    tampered = replace(
        build,
        evidence_records=(replace(record, snapshot_text="api_key=raw-secret-canary"),),
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

    with pytest.raises(ValueError, match="canonical|snapshot"):
        await persist_session_plan(db_session, session_id=session.id, build=tampered)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tampered_question",
    [
        PlannedQuestion(text=" Question 1 ", category="behavioural"),
        PlannedQuestion(text="Question 1\r\ncontinued", category="behavioural"),
        PlannedQuestion(text="Question 1", category="Behavioural"),
        PlannedQuestion(text="x" * 10_001, category="behavioural"),
    ],
    ids=["whitespace", "crlf", "uppercase-category", "too-long"],
)
async def test_finaliser_rejects_noncanonical_question_builds(
    db_session, tampered_question
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
    claim = await claim_session_setup(
        db_session, session_id=session.id, request=request
    )
    valid = _three_question_build(request)
    bad = replace(valid, questions=(tampered_question, *valid.questions[1:]))

    with pytest.raises(ValueError, match="question"):
        await finalise_session_setup(db_session, claim=claim, build=bad)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["finalise", "fail"])
async def test_setup_terminal_transition_requires_live_async_job(
    db_session, operation: str
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
    job = await db_session.get(AsyncJob, claim.job_id)
    assert job is not None
    job.status = "done"
    await db_session.flush()

    if operation == "finalise":
        changed = await finalise_session_setup(
            db_session, claim=claim, build=_three_question_build(request)
        )
    else:
        changed = await fail_session_setup(
            db_session,
            claim=claim,
            error_code="coach_contract_unsupported",
            retryable=False,
        )
    assert changed is False
    db_session.expire_all()
    persisted = await db_session.get(InterviewSession, session_id)
    assert persisted is not None
    assert persisted.conversation_state == "planning"
    assert persisted.setup_job_id == claim.job_id
