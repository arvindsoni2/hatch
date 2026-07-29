"""Integration tests for /api/coach router — create session, submit answer, end session, 404 handling."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import func, select
from starlette.datastructures import UploadFile as StarletteUploadFile
from starlette.requests import Request as StarletteRequest

from app.main import app
from app.config import settings
from app.models.async_job import AsyncJob
from app.models.coach_session import (
    InterviewSession,
    InterviewSessionEvent,
    SessionQuestion,
    SessionRecording,
)
from app.schemas.coach import (
    AnswerEvaluation,
    CompanyResearchResponse,
    SessionFeedbackReport,
    SessionResponse,
)
from app.services.coach_aggregation import resolve_canonical_attempts

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# ---------------------------------------------------------------------------
# Helpers / shared data
# ---------------------------------------------------------------------------

SAMPLE_SESSION_RESPONSE = SessionResponse(
    id="session-uuid-001",
    application_id=None,
    company_name="Accenture",
    role_title="Solutions Architect",
    status="active",
    overall_score=None,
    questions=[],
    created_at="2026-03-10T09:00:00",
)

SAMPLE_EVALUATION = AnswerEvaluation(
    scores={
        "relevance": 8,
        "star_structure": 7,
        "technical_depth": 8,
        "conciseness": 7,
        "communication": 8,
        "impact_metrics": 7,
    },
    overall=7.5,
    feedback="Good STAR structure with quantified outcomes.",
    strengths=["Clear structure", "Technical depth"],
    improvements=["Add more metrics"],
    follow_up_question=None,
    speech_coaching=[],
)

SAMPLE_REPORT = SessionFeedbackReport(
    session_id="session-uuid-001",
    overall_score=7.5,
    category_scores={"Technical": 8.0, "Behavioural": 7.0},
    executive_summary="Strong performance with clear STAR responses.",
    strengths=["Technical depth", "Quantified outcomes"],
    improvement_areas=["Reduce hedging language"],
    coaching_points=["Practice the STAR framework daily"],
    practice_plan=[
        {
            "day": 1,
            "focus": "STAR Structure",
            "activity": "Practice 3 STAR answers",
            "resource": None,
        }
    ],
    question_evaluations=[],
)

SAMPLE_RESEARCH = CompanyResearchResponse(
    company_name="Accenture",
    sector="Consulting",
    website="https://www.accenture.com",
    description="Global professional services company.",
    recent_news=[],
    key_products=[],
    tech_stack_signals=[],
)


def close_queued_work(_job_id, work, **_kwargs) -> None:
    """Keep the real create transaction while preventing a test worker escape."""
    work.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_session_returns_202(client) -> None:
    """POST /api/coach/sessions returns 202 with job_id (async pattern)."""
    response = await client.post(
        "/api/coach/sessions",
        json={
            "company_name": "Accenture",
            "role_title": "Solutions Architect",
            "config": {"question_count": 5},
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "coach_session"


@pytest.mark.asyncio
async def test_submit_answer_unknown_session_does_not_queue_work(client) -> None:
    """Unknown submissions fail synchronously instead of queuing doomed work."""
    response = await client.post(
        "/api/coach/sessions/session-uuid-001/submit-answer",
        params={"question_id": "q-uuid-001"},
        json={
            "transcript": "In my previous role at a FTSE 100 company...",
            "duration_ms": 60000,
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_legacy_submit_rejects_conversational_session_without_mutation(
    client, db_session
) -> None:
    """Removing the experience guard would create a legacy recording."""
    session = InterviewSession(
        id="conversation_submit_1",
        company_name="Example Co",
        role_title="Architect",
        config={},
        status="active",
        experience_version="conversational_v1",
        conversation_state="asking",
        state_version=1,
    )
    db_session.add(session)
    await db_session.commit()

    response = await client.post(
        f"/api/coach/sessions/{session.id}/submit-answer",
        params={"question_id": "question_1"},
        json={"transcript": "synthetic"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "coach_conversational_command_required"
    assert (
        await db_session.scalar(
            select(func.count(SessionRecording.id)).where(
                SessionRecording.session_id == session.id
            )
        )
        == 0
    )


@pytest.mark.asyncio
async def test_legacy_end_and_retry_reject_conversational_session_before_side_effects(
    client, db_session
) -> None:
    """Removing either guard would let a legacy lifecycle flow mutate this row."""
    session = InterviewSession(
        id="conversation_lifecycle_1",
        company_name="Example Co",
        role_title="Architect",
        config={},
        status="setup",
        experience_version="conversational_v1",
        conversation_state="ready",
        state_version=0,
    )
    db_session.add(session)
    await db_session.commit()

    end_response = await client.post(f"/api/coach/sessions/{session.id}/end")
    retry_response = await client.post(f"/api/coach/sessions/{session.id}/retry")

    assert end_response.status_code == 409
    assert (
        end_response.json()["error"]["code"] == "coach_conversational_command_required"
    )
    assert retry_response.status_code == 409
    assert (
        retry_response.json()["error"]["code"]
        == "coach_conversational_session_retry_unsupported"
    )
    await db_session.refresh(session)
    assert (session.status, session.conversation_state) == ("setup", "ready")


@pytest.mark.asyncio
async def test_legacy_skip_rejects_conversational_session_before_reconciliation_or_write(
    client, db_session
) -> None:
    """Experience dispatch must precede legacy reconciliation and skip persistence."""
    session = InterviewSession(
        id="conversation-legacy-skip-guard",
        company_name="Example Co",
        role_title="Architect",
        config={},
        status="active",
        experience_version="conversational_v1",
        conversation_state="asking",
        state_version=7,
        activity_version=4,
    )
    question = SessionQuestion(
        id="conversation-legacy-skip-question",
        session_id=session.id,
        question_num=1,
        text="Explain the trade-off.",
        category="technical",
        difficulty="realistic",
        order_in_session=1,
        question_kind="planned",
        question_state="asked",
        asked_sequence=1,
    )
    session.active_question_id = question.id
    session.active_root_question_id = question.id
    db_session.add_all((session, question))
    await db_session.commit()
    session_id = session.id
    question_id = question.id

    response = await client.post(
        f"/api/coach/sessions/{session_id}/skip",
        params={"question_id": question_id},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "coach_conversational_command_required"
    db_session.expire_all()
    persisted = await db_session.get(InterviewSession, session_id)
    assert persisted is not None
    assert (
        persisted.status,
        persisted.conversation_state,
        persisted.state_version,
        persisted.activity_version,
    ) == ("active", "asking", 7, 4)
    assert (
        await db_session.scalar(
            select(func.count(SessionRecording.id)).where(
                SessionRecording.session_id == session_id
            )
        )
        == 0
    )


@pytest.mark.asyncio
async def test_conversational_delete_persists_abandoned_pair_and_fences_owned_work(
    client, db_session
) -> None:
    """Changing only coarse status leaves an invalid lifecycle and live workers."""
    session = InterviewSession(
        id="conversation-delete-processing",
        company_name="Example Co",
        role_title="Architect",
        config={},
        status="active",
        experience_version="conversational_v1",
        conversation_state="processing_answer",
        state_version=9,
        activity_version=3,
        setup_generation=2,
        setup_job_id="stale-setup-job",
        setup_claim_token="stale-setup-token",
        setup_claimed_at=datetime.utcnow(),
        setup_claim_expires_at=datetime.utcnow(),
        report_state="building",
        report_job_id="stale-report-job",
    )
    question = SessionQuestion(
        id="conversation-delete-question",
        session_id=session.id,
        question_num=1,
        text="Explain the trade-off.",
        category="technical",
        difficulty="realistic",
        order_in_session=1,
        question_kind="planned",
        question_state="asked",
        asked_sequence=1,
    )
    attempt = SessionRecording(
        id="conversation-delete-attempt",
        session_id=session.id,
        question_id=question.id,
        recording_type="text",
        attempt_number=1,
        attempt_kind="primary",
        attempt_state="pending_processing",
        evaluation_state="pending",
        processing_generation=5,
        processing_retry_limit=2,
        async_job_id="stale-processing-job",
        client_attempt_id="conversation-delete-client",
    )
    session.active_question_id = question.id
    session.active_root_question_id = question.id
    session.active_recording_id = attempt.id
    db_session.add_all((session, question, attempt))
    await db_session.commit()
    session_id = session.id
    attempt_id = attempt.id

    response = await client.delete(f"/api/coach/sessions/{session_id}")

    assert response.status_code == 204
    db_session.expire_all()
    persisted = await db_session.get(InterviewSession, session_id)
    persisted_attempt = await db_session.get(SessionRecording, attempt_id)
    assert persisted is not None and persisted_attempt is not None
    assert (persisted.status, persisted.conversation_state) == (
        "abandoned",
        "abandoned",
    )
    assert persisted.state_version == 10
    assert persisted.setup_generation == 3
    assert (
        persisted.setup_job_id,
        persisted.setup_claim_token,
        persisted.report_job_id,
        persisted.active_recording_id,
    ) == (None, None, None, None)
    assert persisted_attempt.processing_generation == 6
    assert persisted_attempt.async_job_id is None
    events = (
        await db_session.scalars(
            select(InterviewSessionEvent).where(
                InterviewSessionEvent.session_id == session_id
            )
        )
    ).all()
    assert [
        (event.event_type, event.state_before, event.state_after) for event in events
    ] == [("session_abandoned", "processing_answer", "abandoned")]


@pytest.mark.asyncio
async def test_legacy_delete_keeps_existing_coarse_status_behavior(
    client, db_session
) -> None:
    """Conversational dispatch must not add state/event mutations to legacy rows."""
    session = InterviewSession(
        id="legacy-delete-contract",
        company_name="Legacy Co",
        role_title="Architect",
        config={},
        status="active",
        experience_version="legacy_v1",
        state_version=0,
    )
    db_session.add(session)
    await db_session.commit()

    response = await client.delete(f"/api/coach/sessions/{session.id}")

    assert response.status_code == 204
    await db_session.refresh(session)
    assert (session.status, session.conversation_state, session.state_version) == (
        "abandoned",
        None,
        0,
    )
    assert (
        await db_session.scalar(
            select(func.count(InterviewSessionEvent.id)).where(
                InterviewSessionEvent.session_id == session.id
            )
        )
        == 0
    )


@pytest.mark.asyncio
async def test_legacy_submit_audio_rejects_conversation_before_media_or_job_side_effects(
    client, db_session, monkeypatch, tmp_path
) -> None:
    """Moving the guard below media handling would create files, jobs, or recordings."""
    session = InterviewSession(
        id="conversation_audio_1",
        company_name="Example Co",
        role_title="Architect",
        config={},
        status="active",
        experience_version="conversational_v1",
        conversation_state="asking",
        state_version=1,
    )
    db_session.add(session)
    await db_session.commit()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    response = await client.post(
        f"/api/coach/sessions/{session.id}/submit-audio",
        data={"question_id": "question_1"},
        files={"audio": ("answer.txt", b"not-audio", "text/plain")},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "coach_conversational_command_required"
    assert (
        await db_session.scalar(
            select(func.count(SessionRecording.id)).where(
                SessionRecording.session_id == session.id
            )
        )
        == 0
    )
    assert await db_session.scalar(select(func.count(AsyncJob.id))) == 0
    assert not (tmp_path / "recordings" / session.id).exists()
    await db_session.refresh(session)
    assert (session.status, session.conversation_state, session.state_version) == (
        "active",
        "asking",
        1,
    )


@pytest.mark.asyncio
async def test_conversational_submit_audio_rejects_before_multipart_form_parsing(
    client, db_session, monkeypatch
) -> None:
    """Binding multipart before the experience guard would call this parser sentinel."""
    session = InterviewSession(
        id="conversation_audio_parser_1",
        company_name="Example Co",
        role_title="Architect",
        config={},
        status="active",
        experience_version="conversational_v1",
        conversation_state="asking",
        state_version=1,
    )
    db_session.add(session)
    await db_session.commit()

    async def fail_if_form_is_parsed(_request):
        raise AssertionError(
            "multipart form parsing must not run for conversational audio"
        )

    monkeypatch.setattr(StarletteRequest, "form", fail_if_form_is_parsed)

    response = await client.post(
        f"/api/coach/sessions/{session.id}/submit-audio",
        data={"question_id": "question_1"},
        files={"audio": ("answer.webm", b"not-audio", "audio/webm")},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "coach_conversational_command_required"


@pytest.mark.asyncio
async def test_flag_off_rejects_new_conversation_but_preserves_legacy_create(
    client, monkeypatch
) -> None:
    """Incorrect feature dispatch would either admit v1 or break the legacy 202."""
    monkeypatch.setattr(settings, "HATCH_COACH_CONVERSATIONAL_ENABLED", False)
    conversational = await client.post(
        "/api/coach/sessions",
        json={
            "company_name": "Example Co",
            "role_title": "Architect",
            "jd_text": "Build resilient systems.",
            "experience_version": "conversational_v1",
            "conversational_config": {
                "interview_type": "mixed",
                "difficulty": "realistic",
                "duration_minutes": 30,
                "planned_question_count": 6,
                "role_family": "solution_architecture",
                "role_level": "senior",
                "industry": "technology",
                "locale": "en-GB",
                "focus_areas": ["architecture"],
                "allowed_answer_modes": ["text"],
                "evidence_selection": {
                    "application_cv": "none",
                    "master_cv": "exclude",
                    "question_bank": "exclude",
                    "company_research": "exclude",
                    "draft_evidence_consent": False,
                },
            },
        },
    )
    with patch(
        "app.services.coach_session_queue.AsyncJobService.run",
        side_effect=close_queued_work,
    ):
        legacy = await client.post(
            "/api/coach/sessions",
            json={"company_name": "Example Co", "role_title": "Architect"},
        )

    assert conversational.status_code == 403
    assert conversational.json()["error"]["code"] == "coach_conversation_not_enabled"
    assert legacy.status_code == 202


@pytest.mark.asyncio
async def test_omitted_experience_creation_persists_legacy_v1_stub(
    client, db_session
) -> None:
    """Changing the omitted-version dispatch branch would route a legacy create elsewhere."""
    with patch(
        "app.services.coach_session_queue.AsyncJobService.run",
        side_effect=close_queued_work,
    ):
        response = await client.post(
            "/api/coach/sessions",
            json={"company_name": "Legacy Co", "role_title": "Engineer"},
        )

    assert response.status_code == 202
    session = await db_session.get(InterviewSession, response.json()["session_id"])
    assert session is not None
    assert (session.experience_version, session.conversation_state) == (
        "legacy_v1",
        None,
    )


def test_legacy_canonical_resolver_selects_latest_valid_completed_attempt() -> None:
    """Selecting the latest terminal row instead would discard the legacy completed score."""
    question = SessionQuestion(
        id="legacy-resolver-question",
        session_id="legacy-resolver-session",
        question_num=1,
        text="Describe a delivery.",
        category="Behavioural",
        difficulty="medium",
        order_in_session=1,
    )
    completed = SessionRecording(
        id="legacy-resolver-completed",
        session_id="legacy-resolver-session",
        question_id=question.id,
        recording_type="video",
        evaluation_state="completed",
        created_at=datetime(2026, 7, 1, 9, 0, 0),
        evaluation_json=json.dumps(
            {
                "evaluation_state": "completed",
                "scores": {
                    "relevance": 8,
                    "star_structure": 7,
                    "technical_depth": 9,
                    "conciseness": 6,
                    "communication": 8,
                    "impact_metrics": 7,
                },
                "overall": 7.5,
            }
        ),
    )
    later_unavailable = SessionRecording(
        id="legacy-resolver-unavailable",
        session_id="legacy-resolver-session",
        question_id=question.id,
        recording_type="video",
        evaluation_state="unavailable",
        created_at=datetime(2026, 7, 1, 9, 5, 0),
    )

    resolved = resolve_canonical_attempts([question], [completed, later_unavailable])

    assert len(resolved) == 1
    assert resolved[0].recording is completed
    assert resolved[0].evaluation is not None
    assert resolved[0].evaluation.overall == 7.5
    assert resolved[0].latest_terminal_state == "unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {
            "experience_version": "conversational_v1",
            "company_name": "Bearer top-level-private-token",
            "role_title": "Architect",
            "conversational_config": {"nested_canary": "Bearer nested-private-token"},
        },
        {
            "experience_version": "conversational_v1",
            "company_name": "Example Co",
            "role_title": "Architect",
            "top_level_canary": "Bearer top-level-private-token",
        },
    ],
)
async def test_malformed_conversational_create_redacts_all_client_canaries(
    client, caplog, payload
) -> None:
    """Returning FastAPI validation details would reflect malformed conversational input."""
    response = await client.post("/api/coach/sessions", json=payload)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "coach_contract_unsupported"
    assert response.json()["error"]["details"] == {}
    for canary in ("top-level-private-token", "nested-private-token"):
        assert canary not in response.text
        assert canary not in caplog.text


@pytest.mark.asyncio
async def test_draft_consent_validation_returns_exact_safe_registered_error(
    client, caplog
) -> None:
    canary = "private-draft-consent-canary"
    response = await client.post(
        "/api/coach/sessions",
        json={
            "company_name": "Example Co",
            "role_title": "Architect",
            "jd_text": "Build resilient systems.",
            "experience_version": "conversational_v1",
            "conversational_config": {
                "interview_type": "mixed",
                "difficulty": "realistic",
                "duration_minutes": 30,
                "planned_question_count": 6,
                "role_family": "solution_architecture",
                "role_level": "senior",
                "industry": "technology",
                "locale": "en-GB",
                "focus_areas": ["architecture"],
                "allowed_answer_modes": ["text"],
                "evidence_selection": {
                    "application_cv": "none",
                    "master_cv": "exclude",
                    "question_bank": "include_drafts",
                    "selected_question_bank_record_ids": [canary],
                    "company_research": "exclude",
                    "draft_evidence_consent": False,
                },
            },
        },
    )

    assert response.status_code == 422
    body = response.json()
    correlation_id = body["error"].pop("correlation_id")
    assert len(correlation_id) == 32 and correlation_id.isalnum()
    assert body == {
        "error": {
            "code": "coach_draft_evidence_consent_required",
            "message": "Consent is required before draft evidence can be used.",
            "retryable": False,
            "current_state": None,
            "current_state_version": None,
            "details": {},
        }
    }
    assert canary not in response.text
    assert canary not in caplog.text


@pytest.mark.asyncio
async def test_form_encoded_conversational_create_redacts_all_client_canaries(
    client, caplog
) -> None:
    """Treating a form body as opaque bytes would reflect both canaries in FastAPI's 422."""
    response = await client.post(
        "/api/coach/sessions",
        data={
            "experience_version": "conversational_v1",
            "company_name": "Bearer top-level-form-private-token",
            "role_title": "Architect",
            "conversational_config": '{"nested":"Bearer nested-form-private-token"}',
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "coach_contract_unsupported"
    assert response.json()["error"]["details"] == {}
    for canary in ("top-level-form-private-token", "nested-form-private-token"):
        assert canary not in response.text
        assert canary not in caplog.text


@pytest.mark.asyncio
async def test_form_create_classification_has_no_field_count_bypass(
    client, caplog
) -> None:
    """Adding a 33rd field must not exhaust the v1 redaction discriminator."""
    fields = [(f"padding_{index}", "x") for index in range(30)]
    fields.extend(
        [
            ("experience_version", "conversational_v1"),
            ("company_name", "Bearer field-count-private-token"),
            ("role_title", "Architect"),
        ]
    )

    response = await client.post(
        "/api/coach/sessions",
        content=urlencode(fields).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert len(fields) == 33
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "coach_contract_unsupported"
    assert response.json()["error"]["details"] == {}
    assert "field-count-private-token" not in response.text
    assert "field-count-private-token" not in caplog.text


@pytest.mark.asyncio
async def test_form_create_classification_scans_the_final_field(client, caplog) -> None:
    """Padding before the sole v1 discriminator must not expose the body."""
    fields = [
        ("company_name", "Bearer final-field-private-token"),
        ("role_title", "Architect"),
        *((f"padding_{index}", "x") for index in range(40)),
        ("experience_version", "conversational_v1"),
    ]

    response = await client.post(
        "/api/coach/sessions",
        content=urlencode(fields).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert fields[-1] == ("experience_version", "conversational_v1")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "coach_contract_unsupported"
    assert "final-field-private-token" not in response.text
    assert "final-field-private-token" not in caplog.text


@pytest.mark.asyncio
async def test_form_create_classification_scans_the_full_schema_ceiling(
    client, caplog
) -> None:
    """A maximum-codepoint JD may encode above any arbitrary raw-byte cutoff."""
    canary = "schema-ceiling-private-token"
    large_jd = "\N{POUND SIGN}" * (100_000 - len(canary)) + canary
    fields = [
        ("company_name", "Example Co"),
        ("role_title", "Architect"),
        ("jd_text", large_jd),
        ("experience_version", "conversational_v1"),
    ]
    encoded = urlencode(fields).encode()

    response = await client.post(
        "/api/coach/sessions",
        content=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert len(large_jd) == 100_000
    assert len(encoded) > 128 * 1024
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "coach_contract_unsupported"
    assert canary not in response.text
    assert canary not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "discriminators",
    [
        ("conversational_v1", "conversational_v1"),
        ("legacy_v1", "conversational_v1"),
    ],
    ids=["duplicate-same", "duplicate-conflicting"],
)
async def test_form_create_classification_preserves_ambiguous_duplicates(
    client, discriminators
) -> None:
    """Accepting either duplicate discriminator would guess the request contract."""
    fields = [
        ("experience_version", discriminators[0]),
        ("company_name", "duplicate-discriminator-private-token"),
        ("experience_version", discriminators[1]),
    ]

    response = await client.post(
        "/api/coach/sessions",
        content=urlencode(fields).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "model_attributes_type"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        b"experience_version=conversational_v1%ZZ",
        b"experience_version=conversational_v1&experience_version=%",
        b"experience_version=%E2%28%A1",
    ],
    ids=["bad-hex", "malformed-duplicate", "invalid-utf8"],
)
async def test_form_create_classification_preserves_malformed_discriminators(
    client, content
) -> None:
    """A malformed discriminator is ambiguous and retains framework validation."""
    response = await client.post(
        "/api/coach/sessions",
        content=content + b"&company_name=malformed-discriminator-private-token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "model_attributes_type"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unrelated_field",
    [
        b"company_name=encoded-discriminator-private-token%ZZ",
        b"company_name=encoded-discriminator-private-token%FF",
        (
            b"company_name=encoded-discriminator-private-token%26"
            b"experience_version%3Dlegacy_v1"
        ),
    ],
    ids=["malformed-percent", "invalid-utf8", "encoded-delimiters"],
)
async def test_form_create_classification_decodes_only_discriminator_components(
    client, caplog, unrelated_field
) -> None:
    """Encoded key/value bytes must identify v1 without decoding unrelated values."""
    response = await client.post(
        "/api/coach/sessions",
        content=(unrelated_field + b"&%65xperience%5Fversion=conversational%5fv1"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "coach_contract_unsupported"
    assert "encoded-discriminator-private-token" not in response.text
    assert "encoded-discriminator-private-token" not in caplog.text


@pytest.mark.asyncio
async def test_form_create_classification_counts_encoded_duplicate_names(
    client,
) -> None:
    """Counting raw spellings would miss a percent-encoded duplicate key alias."""
    response = await client.post(
        "/api/coach/sessions",
        content=(
            b"experience_version=conversational_v1&"
            b"experience%5fversion=conversational_v1&"
            b"company_name=encoded-duplicate-private-token"
        ),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "model_attributes_type"


@pytest.mark.asyncio
async def test_form_create_classification_covers_the_maximum_jd_length(client) -> None:
    """An allowed-size JD must not push the v1 discriminator past the safety bound."""
    large_jd = "x" * 99_976 + "large-form-private-token"

    response = await client.post(
        "/api/coach/sessions",
        data={
            "experience_version": "conversational_v1",
            "company_name": "Example Co",
            "role_title": "Architect",
            "jd_text": large_jd,
        },
    )

    assert len(large_jd) == 100_000
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "coach_contract_unsupported"
    assert "large-form-private-token" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "content_type", "expected_status"),
    [
        (
            b"experience_version=legacy_v1&company_name=legacy-form-private-token",
            "application/x-www-form-urlencoded",
            422,
        ),
        (
            b"company_name=missing-discriminator-private-token",
            "application/x-www-form-urlencoded",
            422,
        ),
        (
            b"experience_version=conversational_v1&company_name=wrong-type-private-token",
            "text/plain",
            400,
        ),
        (
            b"experience_version=legacy_v1&experience_version=conversational_v1",
            "application/x-www-form-urlencoded",
            422,
        ),
    ],
)
async def test_create_redaction_does_not_guess_legacy_or_ambiguous_raw_bodies(
    client, content, content_type, expected_status
) -> None:
    """Fail closed for a recognized v1 body without guessing legacy/ambiguous inputs."""
    response = await client.post(
        "/api/coach/sessions",
        content=content,
        headers={"Content-Type": content_type},
    )

    assert response.status_code == expected_status
    if expected_status == 400:
        assert response.json()["error"]["code"] == "coach_contract_unsupported"
        assert "wrong-type-private-token" not in response.text
    else:
        assert response.json()["detail"][0]["type"] == "model_attributes_type"


@pytest.mark.asyncio
async def test_malformed_legacy_create_keeps_framework_validation_behavior(
    client,
) -> None:
    """Classifying every malformed create as conversational would break legacy clients."""
    response = await client.post(
        "/api/coach/sessions",
        json={"company_name": "Example Co", "role_title": ["not", "a", "string"]},
    )

    assert response.status_code == 422
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_legacy_submit_audio_missing_file_keeps_typed_validation_body(
    client,
) -> None:
    """Replacing typed File validation with a string detail breaks legacy clients."""
    response = await client.post(
        "/api/coach/sessions/legacy-audio-validation/submit-audio",
        data={"question_id": "question-1"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": [
            {
                "type": "missing",
                "loc": ["body", "audio"],
                "msg": "Field required",
                "input": None,
            }
        ]
    }


@pytest.mark.asyncio
async def test_legacy_submit_audio_json_keeps_both_missing_field_errors(client) -> None:
    """A non-multipart body must retain the former File/Form validation order and shape."""
    response = await client.post(
        "/api/coach/sessions/legacy-audio-validation/submit-audio",
        json={"question_id": "question-1"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": [
            {
                "type": "missing",
                "loc": ["body", "question_id"],
                "msg": "Field required",
                "input": None,
            },
            {
                "type": "missing",
                "loc": ["body", "audio"],
                "msg": "Field required",
                "input": None,
            },
        ]
    }


@pytest.mark.asyncio
async def test_legacy_submit_audio_rejects_text_in_the_file_field(client) -> None:
    """Accepting a plain form string as audio would bypass typed UploadFile validation."""
    response = await client.post(
        "/api/coach/sessions/legacy-audio-validation/submit-audio",
        data={"question_id": "question-1", "audio": "not-a-file"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": [
            {
                "type": "value_error",
                "loc": ["body", "audio"],
                "msg": "Value error, Expected UploadFile, received: <class 'str'>",
                "input": "not-a-file",
                "ctx": {"error": {}},
            }
        ]
    }


@pytest.mark.asyncio
async def test_legacy_submit_audio_rejects_file_shaped_face_summary(
    client, monkeypatch
) -> None:
    """Ignoring a non-string face_summary regresses the former typed Form contract."""
    closed_uploads = []
    original_close = StarletteUploadFile.close

    async def track_close(upload):
        closed_uploads.append(upload.filename)
        await original_close(upload)

    monkeypatch.setattr(StarletteUploadFile, "close", track_close)
    response = await client.post(
        "/api/coach/sessions/legacy-audio-validation/submit-audio",
        data={"question_id": "question-1"},
        files={
            "audio": ("answer.wav", b"RIFF", "audio/wav"),
            "face_summary": ("face.json", b"{}", "application/json"),
        },
    )

    assert response.status_code == 422
    error = response.json()["detail"]
    assert len(error) == 1
    assert {key: error[0][key] for key in ("type", "loc", "msg")} == {
        "type": "string_type",
        "loc": ["body", "face_summary"],
        "msg": "Input should be a valid string",
    }
    assert error[0]["input"]["filename"] == "face.json"
    assert error[0]["input"]["size"] == 2
    assert error[0]["input"]["headers"]["content-type"] == "application/json"
    assert closed_uploads == ["answer.wav", "face.json"]


@pytest.mark.asyncio
async def test_legacy_submit_audio_preserves_the_size_limit(
    client, monkeypatch
) -> None:
    """Compatibility parsing must not skip the established audio-size fence."""
    monkeypatch.setattr("app.routers.coach._MAX_AUDIO_BYTES", 3)

    response = await client.post(
        "/api/coach/sessions/legacy-audio-validation/submit-audio",
        data={"question_id": "question-1"},
        files={"audio": ("answer.wav", b"RIFF", "audio/wav")},
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "Audio file exceeds 50 MB limit"}


@pytest.mark.asyncio
async def test_legacy_submit_audio_happy_path_still_returns_202(
    client, db_session, monkeypatch, tmp_path
) -> None:
    """Compatibility validation must continue to admit the legacy multipart contract."""
    session_id = "legacy-audio-happy"
    question_id = "legacy-question-happy"
    db_session.add(
        InterviewSession(
            id=session_id,
            company_name="Example Co",
            role_title="Architect",
            config={"question_count": 1},
            status="active",
            experience_version="legacy_v1",
        )
    )
    db_session.add(
        SessionQuestion(
            id=question_id,
            session_id=session_id,
            question_num=1,
            text="Tell me about a delivery challenge.",
            category="Behavioural",
            difficulty="medium",
            order_in_session=1,
        )
    )
    await db_session.commit()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    with patch(
        "app.routers.coach.AsyncJobService.run",
        side_effect=close_queued_work,
    ):
        response = await client.post(
            f"/api/coach/sessions/{session_id}/submit-audio",
            data={"question_id": question_id, "face_summary": "{}"},
            files={"audio": ("answer.wav", b"RIFF", "audio/wav")},
        )

    assert response.status_code == 202
    assert response.json()["type"] == "submit_audio"


@pytest.mark.asyncio
async def test_capabilities_truthfully_describes_conversation_and_video_support(
    client, monkeypatch
) -> None:
    """Omitting the feature flag or claiming video support must fail this test."""
    monkeypatch.setattr(settings, "HATCH_COACH_CONVERSATIONAL_ENABLED", False)

    response = await client.get("/api/coach/capabilities")

    assert response.status_code == 200
    assert response.json()["conversational"] is False
    assert response.json()["video_analysis_for_conversational"] is False


@pytest.mark.asyncio
async def test_capabilities_publish_the_literal_conversational_contract(
    client, monkeypatch
) -> None:
    """Advertising unimplemented PR1 media or turn detection would mislead clients."""
    monkeypatch.setattr(settings, "HATCH_COACH_CONVERSATIONAL_ENABLED", False)
    monkeypatch.setattr(settings, "HATCH_COACH_AUTO_TURN_DETECTION_ENABLED", True)

    response = await client.get("/api/coach/capabilities")

    assert response.status_code == 200
    capabilities = response.json()
    assert {
        key: capabilities[key]
        for key in (
            "conversational_interview",
            "typed_answers",
            "audio_upload",
            "automatic_turn_detection",
            "audio_retention_default",
            "video_analysis_for_conversational",
            "contract_version",
        )
    } == {
        "conversational_interview": False,
        "typed_answers": True,
        "audio_upload": False,
        "automatic_turn_detection": "none",
        "audio_retention_default": "delete_after_processing",
        "video_analysis_for_conversational": False,
        "contract_version": "coach_capabilities_v2",
    }
    assert capabilities["transcription"] == {
        "available": False,
        "provider_type": "none",
    }
    assert capabilities["evaluation"] == {
        "available": False,
        "provider_type": "none",
    }


@pytest.mark.asyncio
async def test_capabilities_fail_closed_when_profile_loading_fails(
    client, monkeypatch
) -> None:
    """A profile-load fallback must not advertise profile-derived capabilities."""
    monkeypatch.setattr(
        "app.agents.tools.profile_loader.load_profile",
        lambda: (_ for _ in ()).throw(RuntimeError("profile unavailable")),
    )

    response = await client.get("/api/coach/capabilities")

    assert response.status_code == 200
    capabilities = response.json()
    assert capabilities["face_analysis"] is False
    assert capabilities["tts"] is False
    assert capabilities["transcription"] == {
        "available": False,
        "provider_type": "none",
    }


@pytest.mark.asyncio
async def test_session_list_additively_exposes_conversational_summary(
    client, db_session
) -> None:
    """Dropping the persisted mode or retention summary would hide live routing data."""
    session = InterviewSession(
        id="conversation_summary_1",
        company_name="Example Co",
        role_title="Architect",
        config={},
        status="setup",
        experience_version="conversational_v1",
        conversation_state="ready",
        retention_policy_json={
            "audio": "delete_after_processing",
            "transcript": "retain",
        },
    )
    db_session.add(session)
    await db_session.commit()

    response = await client.get("/api/coach/sessions")

    assert response.status_code == 200
    summary = next(item for item in response.json() if item["id"] == session.id)
    assert summary["experience_version"] == "conversational_v1"
    assert summary["conversation_state"] == "ready"
    assert summary["retention_summary"] == {
        "audio": "delete_after_processing",
        "transcript": "retain",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("retention_policy", "expected_summary"),
    [
        (
            {"audio": "retain_until_deleted", "transcript": "retain"},
            {"audio": "retain_until_deleted", "transcript": "retain"},
        ),
        (
            {
                "audio": "delete_after_processing",
                "transcript": "retain",
                "private_canary": "Bearer retention-private-token",
            },
            {"audio": "delete_after_processing", "transcript": "retain"},
        ),
        (["Bearer retention-private-token"], None),
        ({"audio": "unapproved", "transcript": "retain"}, None),
    ],
)
async def test_list_and_detail_project_only_bounded_retention_summaries(
    client, db_session, retention_policy, expected_summary
) -> None:
    """Copying persisted retention JSON would expose extra or malformed private data."""
    session = InterviewSession(
        id="conversation_retention_projection_1",
        company_name="Example Co",
        role_title="Architect",
        config={},
        status="setup",
        experience_version="conversational_v1",
        conversation_state="ready",
        retention_policy_json=retention_policy,
    )
    db_session.add(session)
    await db_session.commit()

    listed = await client.get("/api/coach/sessions")
    detail = await client.get(f"/api/coach/sessions/{session.id}")

    assert listed.status_code == 200
    assert detail.status_code == 200
    list_summary = next(item for item in listed.json() if item["id"] == session.id)
    assert list_summary["retention_summary"] == expected_summary
    assert detail.json()["retention_summary"] == expected_summary
    assert "retention-private-token" not in listed.text
    assert "retention-private-token" not in detail.text


@pytest.mark.asyncio
async def test_end_session_unknown_returns_404(client) -> None:
    """An unknown session cannot create an orphan report job."""
    response = await client.post("/api/coach/sessions/session-uuid-001/end")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_session_not_found_returns_404() -> None:
    """GET /api/coach/sessions/{id} returns 404 for a missing session."""
    with patch("app.routers.coach.CoachService") as MockSvc:
        instance = MockSvc.return_value
        from fastapi import HTTPException

        instance.get_session = AsyncMock(
            side_effect=HTTPException(status_code=404, detail="Session not found")
        )
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/coach/sessions/nonexistent-id")
    assert response.status_code == 404
    assert "Session not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_research_company_returns_200() -> None:
    """POST /api/coach/research returns 200 with CompanyResearchResponse."""
    with patch("app.routers.coach.CoachService") as MockSvc:
        instance = MockSvc.return_value
        instance.research_company = AsyncMock(return_value=SAMPLE_RESEARCH)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/coach/research",
                params={"company_name": "Accenture", "sector": "Consulting"},
            )
    assert response.status_code == 200
    data = response.json()
    assert data["company_name"] == "Accenture"


@pytest.mark.asyncio
async def test_list_sessions_returns_200() -> None:
    """GET /api/coach/sessions returns 200 with a list."""
    with patch("app.routers.coach.CoachService") as MockSvc:
        instance = MockSvc.return_value
        instance.list_sessions = AsyncMock(return_value=[])
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/coach/sessions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_get_research_not_found_returns_404(client: AsyncClient) -> None:
    """GET /api/coach/research/{company_name} returns 404 when no cached research exists."""
    response = await client.get("/api/coach/research/UnknownCompanyXYZ")
    assert response.status_code == 404
    assert "No cached research" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_session_not_found_returns_404(client: AsyncClient) -> None:
    """DELETE /api/coach/sessions/{id} returns 404 for a non-existent session."""
    response = await client.delete("/api/coach/sessions/nonexistent-session-id")
    assert response.status_code == 404
    assert "Session not found" in response.json()["detail"]


# ---------------------------------------------------------------------------
# SEC-3: path traversal guards on submit-audio
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_audio_rejects_traversal_in_question_id(
    client: AsyncClient, tmp_path
) -> None:
    """submit-audio must reject question_id containing path traversal chars."""
    audio_bytes = b"RIFF" + b"\x00" * 36  # minimal dummy
    response = await client.post(
        "/api/coach/sessions/valid-session-id/submit-audio",
        data={"question_id": "../../etc/passwd"},
        files={"audio": ("answer.webm", audio_bytes, "audio/webm")},
    )
    assert response.status_code == 400
    assert "question_id" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_submit_audio_rejects_traversal_in_session_id(tmp_path) -> None:
    """submit-audio must reject session_id containing path traversal chars."""
    audio_bytes = b"RIFF" + b"\x00" * 36
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/coach/sessions/../foo/submit-audio",
            data={"question_id": "valid-question-id"},
            files={"audio": ("answer.webm", audio_bytes, "audio/webm")},
        )
    # FastAPI will match /api/coach/sessions/{session_id=..}/foo/submit-audio differently;
    # the path normalisation at the HTTP layer means the session_id param itself contains
    # only the URL-decoded segment, which our regex rejects.
    assert response.status_code in (400, 404)


@pytest.mark.asyncio
async def test_submit_audio_accepts_valid_ids(
    client: AsyncClient, tmp_path, monkeypatch
) -> None:
    """submit-audio accepts UUIDs and slug IDs."""
    import uuid as _uuid

    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    audio_bytes = b"RIFF" + b"\x00" * 36
    response = await client.post(
        f"/api/coach/sessions/{_uuid.uuid4()}/submit-audio",
        data={"question_id": str(_uuid.uuid4())},
        files={"audio": ("answer.webm", audio_bytes, "audio/webm")},
    )
    # Unknown-but-safe IDs are rejected synchronously, never a path-operation 500.
    assert response.status_code in (400, 404, 422)


@pytest.mark.asyncio
async def test_get_next_question_with_mock_service() -> None:
    """GET /api/coach/sessions/{id}/next-question returns 200 (null) with mocked service."""
    with patch("app.routers.coach.CoachService") as MockSvc:
        instance = MockSvc.return_value
        instance.get_next_question = AsyncMock(return_value=None)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/coach/sessions/session-uuid-001/next-question"
            )
    assert response.status_code == 200
    assert response.json() is None


@pytest.mark.asyncio
async def test_get_session_report_with_mock_service(client) -> None:
    """GET /api/coach/sessions/{id}/report returns 200 with a SessionFeedbackReport."""
    with patch("app.routers.coach.CoachService") as MockSvc:
        instance = MockSvc.return_value
        instance.get_report = AsyncMock(return_value=SAMPLE_REPORT)
        response = await client.get("/api/coach/sessions/session-uuid-001/report")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "session-uuid-001"
    assert data["overall_score"] == 7.5


@pytest.mark.asyncio
async def test_legacy_report_snapshot_remains_json_identical(
    client, db_session
) -> None:
    """Regenerating or extending a stored legacy report would change its response JSON."""
    session_id = "legacy-report-fixture"
    expected_json = {
        "session_id": session_id,
        "report_state": "completed",
        "diagnostic": None,
        "overall_score": 7.5,
        "question_count_total": 0,
        "question_count_evaluated": 0,
        "question_count_skipped": 0,
        "question_count_unavailable": 0,
        "question_count_unanswered": 0,
        "category_scores": {"Technical": 8.0, "Behavioural": 7.0},
        "executive_summary": "Strong performance with clear STAR responses.",
        "strengths": ["Technical depth", "Quantified outcomes"],
        "improvement_areas": ["Reduce hedging language"],
        "coaching_points": ["Practice the STAR framework daily"],
        "practice_plan": [
            {
                "day": 1,
                "focus": "STAR Structure",
                "activity": "Practice 3 STAR answers",
                "resource": None,
            }
        ],
        "question_evaluations": [],
    }
    session = InterviewSession(
        id=session_id,
        company_name="Legacy Co",
        role_title="Architect",
        config={},
        status="completed",
        experience_version="legacy_v1",
        overall_score=7.5,
        report_state="completed",
        report_json=expected_json,
    )
    db_session.add(session)
    await db_session.commit()

    response = await client.get(f"/api/coach/sessions/{session_id}/report")

    assert response.status_code == 200
    assert response.json() == expected_json


@pytest.mark.asyncio
async def test_legacy_video_recording_remains_report_readable(
    client, db_session
) -> None:
    """Rejecting historical video rows would turn an existing completed report into a 422."""
    session = InterviewSession(
        id="legacy-video-report",
        company_name="Legacy Co",
        role_title="Architect",
        config={},
        status="completed",
        experience_version="legacy_v1",
    )
    question = SessionQuestion(
        id="legacy-video-question",
        session_id=session.id,
        question_num=1,
        text="Walk through a design decision.",
        category="Technical",
        difficulty="medium",
        order_in_session=1,
    )
    recording = SessionRecording(
        id="legacy-video-recording",
        session_id=session.id,
        question_id=question.id,
        recording_type="video",
        transcript="I chose an event-driven design.",
        video_metrics={"eye_contact_pct": 88.0, "expression": "engaged"},
        evaluation_state="completed",
        evaluation_json=json.dumps(
            {
                "evaluation_state": "completed",
                "scores": {
                    "relevance": 8,
                    "star_structure": 7,
                    "technical_depth": 9,
                    "conciseness": 6,
                    "communication": 8,
                    "impact_metrics": 7,
                },
                "overall": 7.5,
            }
        ),
    )
    db_session.add_all([session, question, recording])
    await db_session.commit()

    response = await client.get(f"/api/coach/sessions/{session.id}/report")

    assert response.status_code == 200
    assert response.json()["overall_score"] == 7.5
    await db_session.refresh(recording)
    assert recording.video_metrics == {"eye_contact_pct": 88.0, "expression": "engaged"}


def test_legacy_openapi_report_schemas_keep_numeric_contract() -> None:
    """Adding conversational report fields or loosening the score maximum breaks legacy clients."""
    schema = app.openapi()["components"]["schemas"]

    assert schema["RubricDimension"]["properties"]["score"]["maximum"] == 10
    assert "session_level" not in schema["SessionFeedbackReport"]["properties"]


@pytest.mark.asyncio
async def test_legacy_progress_and_trend_keep_numeric_scores(
    client, db_session
) -> None:
    """Stringifying persisted scores would break legacy progress and trend consumers."""
    parent = InterviewSession(
        id="legacy-progress-parent",
        application_id="legacy-progress-application",
        company_name="Legacy Co",
        role_title="Architect",
        config={},
        status="completed",
        overall_score=7.5,
        created_at=datetime(2026, 7, 1, 9, 0, 0),
        rubric={"dimensions": {"relevance": {"score": 8}}},
        focus_areas=["relevance"],
    )
    child = InterviewSession(
        id="legacy-progress-child",
        application_id="legacy-progress-application",
        company_name="Legacy Co",
        role_title="Architect",
        config={},
        status="completed",
        overall_score=8.25,
        created_at=datetime(2026, 7, 2, 9, 0, 0),
        parent_session_id=parent.id,
        rubric={"dimensions": {"relevance": {"score": 9}}},
        focus_areas=["communication"],
    )
    db_session.add_all([parent, child])
    await db_session.commit()

    progress = await client.get("/api/coach/progress/legacy-progress-application")
    trend = await client.get(f"/api/coach/progress/{child.id}/trend")

    assert progress.status_code == trend.status_code == 200
    assert [item["overall_score"] for item in progress.json()] == [8.25, 7.5]
    assert [item["overall_score"] for item in trend.json()] == [7.5, 8.25]
    assert [item["rubric_scores"]["relevance"] for item in trend.json()] == [8, 9]


@pytest.mark.asyncio
async def test_legacy_retry_abandons_source_and_queues_a_new_legacy_session(
    client, db_session
) -> None:
    """Reusing the source row or inheriting a conversational version breaks legacy retry chaining."""
    source = InterviewSession(
        id="legacy-retry-source",
        application_id="legacy-retry-application",
        company_name="Legacy Co",
        role_title="Architect",
        config={"question_count": 3, "jd_text": "Design systems."},
        status="failed",
        experience_version="legacy_v1",
    )
    db_session.add(source)
    await db_session.commit()

    with patch(
        "app.services.coach_session_queue.AsyncJobService.run",
        side_effect=close_queued_work,
    ):
        response = await client.post(f"/api/coach/sessions/{source.id}/retry")

    assert response.status_code == 202
    await db_session.refresh(source)
    replacement = await db_session.get(InterviewSession, response.json()["session_id"])
    assert source.status == "abandoned"
    assert replacement is not None
    assert replacement.id != source.id
    assert (replacement.experience_version, replacement.conversation_state) == (
        "legacy_v1",
        None,
    )
    assert replacement.application_id == source.application_id
    assert replacement.parent_session_id is None


@pytest.mark.asyncio
async def test_get_application_progress_returns_empty_list(client: AsyncClient) -> None:
    """GET /api/coach/progress/{application_id} returns empty list on fresh DB."""
    response = await client.get("/api/coach/progress/no-such-application-id")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_skip_question_not_found_returns_404(client: AsyncClient) -> None:
    """POST /api/coach/sessions/{id}/skip returns 404 when question doesn't exist."""
    response = await client.post(
        "/api/coach/sessions/session-uuid-001/skip",
        params={"question_id": "nonexistent-question-id"},
    )
    assert response.status_code == 404
    assert "Question not found" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Phase C: plan-followup + progress trend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_followup_returns_200_or_404() -> None:
    """POST /api/coach/sessions/{id}/plan-followup returns 200 with mock service."""
    from app.schemas.coach import PlanFollowUpResponse

    sample_followup = PlanFollowUpResponse(
        followup_session_id="new-session-uuid",
        focus_areas=["star_structure", "delivery"],
        message="Follow-up session created focusing on: star structure and delivery.",
    )

    with patch("app.routers.coach.CoachService") as MockSvc:
        instance = MockSvc.return_value
        instance.plan_followup_session = AsyncMock(return_value=sample_followup)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/api/coach/sessions/session-uuid-001/plan-followup"
            )

    assert response.status_code == 200
    data = response.json()
    assert data["followup_session_id"] == "new-session-uuid"
    assert "star_structure" in data["focus_areas"]


@pytest.mark.asyncio
async def test_plan_followup_session_not_found_returns_404() -> None:
    """POST /api/coach/sessions/{id}/plan-followup returns 404 when session not found."""
    from fastapi import HTTPException

    with patch("app.routers.coach.CoachService") as MockSvc:
        instance = MockSvc.return_value
        instance.plan_followup_session = AsyncMock(
            side_effect=HTTPException(status_code=404, detail="Session not found")
        )
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post("/api/coach/sessions/nonexistent-id/plan-followup")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_progress_trend_returns_list(client: AsyncClient) -> None:
    """GET /api/coach/progress/{session_id}/trend returns a list (empty for fresh DB)."""
    response = await client.get("/api/coach/progress/nonexistent-session-id/trend")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


# ---------------------------------------------------------------------------
# Phase D: capabilities endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_capabilities_returns_dict() -> None:
    """GET /api/coach/capabilities returns face_analysis and tts flags."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/coach/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert "face_analysis" in data
    assert "tts" in data
    assert isinstance(data["face_analysis"], bool)
    assert isinstance(data["tts"], bool)


# ---------------------------------------------------------------------------
# Phase E: TTS endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tts_question_returns_503_when_disabled(client: AsyncClient) -> None:
    """POST /api/coach/sessions/{id}/tts-question returns 503 when TTS is disabled."""
    from app._exceptions import PerceptionNotAvailableError

    # get_tts is imported locally inside the endpoint via
    # 'from ..agents.tools.perception_factory import get_tts'.
    # We patch the source module where it lives.
    with patch(
        "app.agents.tools.perception_factory.get_tts",
        side_effect=PerceptionNotAvailableError("TTS is disabled"),
    ):
        response = await client.post(
            "/api/coach/sessions/session-uuid-001/tts-question",
            params={"question_id": "q-uuid-001"},
        )
    assert response.status_code == 503
