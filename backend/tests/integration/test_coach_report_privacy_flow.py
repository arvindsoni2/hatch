"""Actual persisted Coach reads/claims, not manufactured terminal responses."""

from datetime import datetime, timedelta
import asyncio
import json

import pytest
from fastapi import HTTPException

from app.config import settings
from app.models.async_job import AsyncJob
from app.models.coach_session import (
    InterviewAttemptEvaluation,
    InterviewAttemptStage,
    InterviewSession,
    SessionRecording,
)
from app.repositories.conversational_session_repository import (
    ConversationalRepositoryError,
    ConversationalSessionRepository,
)
from app.repositories.session_repository import SessionRepository
from app.routers.coach_conversation import (
    get_conversational_report,
    get_conversational_diagnostics,
    export_conversational_report,
)
from app.schemas.coach_conversation import (
    HardDeletionCommandRequest,
    ReportExportRequest,
)
from app.services.coach_conversational_progress import ProgressSelector
from app.services.coach_live_view import CoachLiveViewError, CoachLiveViewService
from app.services.coach_privacy import CoachPrivacyService
from app.services.coach_service import CoachService


ZERO_REPORT_COUNTS = {
    "planned_questions_total": 0,
    "planned_questions_answered": 0,
    "planned_questions_skipped": 0,
    "follow_ups_asked": 0,
    "follow_ups_answered": 0,
    "accepted_attempts": 0,
    "retry_attempts": 0,
    "unavailable_attempts": 0,
    "hints_used": 0,
}


async def read_report_http(factory, session_id):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.database import get_db
    from app.routers.coach_conversation import router

    app = FastAPI()
    app.include_router(router)

    async def request_db():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = request_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get(f"/api/coach/sessions/{session_id}/report")


async def seed_built_report(factory, *, with_audio=False):
    from app.services.coach_conversational_report import build_conversational_report

    async with factory() as db:
        row = synthetic_session(id="readable-report", activity_version=3)
        db.add(row)
        await db.flush()
        if with_audio:
            db.add(
                SessionRecording(
                    id="retained-attempt",
                    session_id=row.id,
                    recording_type="audio",
                    attempt_state="completed",
                    transcript="Synthetic retained transcript",
                    audio_retention_policy="retain_until_deleted",
                    audio_retention_state="retained",
                )
            )
            await db.flush()
        snapshot = await ConversationalSessionRepository(db).load_report_input_snapshot(
            row.id, 3
        )
        row.report_json = build_conversational_report(snapshot).persisted_json()
        row.report_state = "completed"
        await db.commit()
        return dict(row.report_json)


async def test_production_built_report_is_readable_with_all_counts_and_version_headers(
    coach_database,
):
    await seed_built_report(coach_database)
    response = await read_report_http(coach_database, "readable-report")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["counts"] == ZERO_REPORT_COUNTS
    assert body["retention_summary"] == {"attempts": []}
    assert (
        response.headers["x-hatch-session-activity-version"]
        == str(body["activity_version"])
        == "3"
    )
    assert (
        response.headers["x-hatch-retention-version"]
        == str(body["retention_version"])
        == "0"
    )


async def test_report_retention_is_live_without_changing_analytical_snapshot(
    coach_database,
    tmp_path,
):
    from app.schemas.coach_conversation import ConversationCommandRequest
    from app.services.coach_conversation_commands import ConversationCommandService
    import hashlib

    analytical = await seed_built_report(coach_database, with_audio=True)
    before = await read_report_http(coach_database, "readable-report")
    assert before.status_code == 200, before.text
    retained = before.json()["retention_summary"]["attempts"][0]
    assert retained == {
        "attempt_id": "retained-attempt",
        "audio_policy": "retain_until_deleted",
        "audio_state": "retained",
        "transcript_state": "retained",
        "audio_cleanup_retryable": False,
    }
    source = tmp_path / "media" / "readable-report" / "retained-attempt.webm"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.touch()
    async with coach_database() as db:
        attempt = await db.get(SessionRecording, "retained-attempt")
        attempt.audio_uri = str(source)
        attempt.audio_content_hash = hashlib.sha256(b"").hexdigest()
        row = await db.get(InterviewSession, "readable-report")
        row.status = "completed"
        row.conversation_state = "completed"
        evaluation = InterviewAttemptEvaluation(
            id="retention-evaluation",
            recording_id=attempt.id,
            version_number=1,
            state="completed",
            evaluation_contract_version="coach_rubric_v1",
            evidence_contract_version="coach_evidence_grounding_v1",
            follow_up_contract_version="coach_follow_up_v1",
        )
        db.add(evaluation)
        await db.flush()
        for name in ("transcription", "speech_analysis", "audio_cleanup"):
            db.add(
                InterviewAttemptStage(
                    recording_id=attempt.id,
                    evaluation_version_id=evaluation.id,
                    stage_name=name,
                    stage_state="completed",
                    expected_processing_generation=attempt.processing_generation,
                )
            )
        await db.commit()
        await ConversationCommandService(db).execute(
            user_id="local",
            session_id=row.id,
            request=ConversationCommandRequest.model_validate(
                {
                    "command_id": "delete-report-audio",
                    "command_type": "delete_audio",
                    "expected_state_version": row.state_version,
                    "payload": {"attempt_id": attempt.id},
                    "contract_version": "coach_conversation_command_v1",
                }
            ),
        )
    assert not source.exists()
    after = await read_report_http(coach_database, "readable-report")
    assert after.status_code == 200, after.text
    assert after.json()["retention_summary"]["attempts"][0]["audio_state"] == "deleted"
    assert after.json()["activity_version"] == 3
    assert after.json()["retention_version"] > before.json()["retention_version"]
    assert after.headers["x-hatch-retention-version"] == str(
        after.json()["retention_version"]
    )
    async with coach_database() as db:
        row = await db.get(InterviewSession, "readable-report")
        assert row.report_json == analytical
        snapshot = await ConversationalSessionRepository(db).load_export_snapshot(
            row.id,
            ReportExportRequest(
                format="json",
                expected_activity_version=3,
                expected_retention_version=after.json()["retention_version"],
                contract_version="coach_report_export_v1",
            ),
        )
        assert snapshot.retention_summary == after.json()["retention_summary"]


async def test_report_rejects_unknown_fields_and_incomplete_counts(coach_database):
    analytical = await seed_built_report(coach_database)
    for malformed in (
        {**analytical, "unexpected": "rejected"},
        {**analytical, "counts": {"accepted_attempts": 0}},
    ):
        async with coach_database() as db:
            row = await db.get(InterviewSession, "readable-report")
            row.report_json = malformed
            await db.commit()
        response = await read_report_http(coach_database, "readable-report")
        assert response.status_code == 409


async def test_report_read_versions_and_retention_do_not_split_during_cleanup(
    coach_database,
):
    from sqlalchemy import update

    await seed_built_report(coach_database, with_audio=True)

    async def cleanups():
        for version in range(1, 11):
            async with coach_database() as db:
                state = "deleted" if version % 2 else "delete_failed"
                await db.execute(
                    update(SessionRecording)
                    .where(SessionRecording.id == "retained-attempt")
                    .values(audio_retention_state=state)
                )
                await db.execute(
                    update(InterviewSession)
                    .where(InterviewSession.id == "readable-report")
                    .values(retention_version=version)
                )
                await db.commit()

    async def reads():
        async with coach_database() as db:
            # Keep an outdated session identity cached while another connection
            # commits cleanup. Authoritative report reads must bypass that cache.
            await db.get(InterviewSession, "readable-report")
            for _ in range(20):
                response = await get_conversational_report("readable-report", db)
                assert response.status_code == 200
                body = json.loads(response.body)
                version = body["retention_version"]
                state = body["retention_summary"]["attempts"][0]["audio_state"]
                assert state == (
                    "retained"
                    if version == 0
                    else "deleted"
                    if version % 2
                    else "delete_failed"
                )
                assert response.headers["x-hatch-retention-version"] == str(version)
                await db.rollback()

    await asyncio.gather(cleanups(), reads())


async def test_export_snapshot_and_version_recheck_ignore_cached_session_identity(
    coach_database,
):
    from sqlalchemy import update

    await seed_built_report(coach_database, with_audio=True)
    async with coach_database() as db:
        row = await db.get(InterviewSession, "readable-report")
        row.status = row.conversation_state = "completed"
        await db.commit()
    async with coach_database() as reader:
        cached = await reader.get(InterviewSession, "readable-report")
        assert cached.retention_version == 0
        async with coach_database() as writer:
            await writer.execute(
                update(InterviewSession)
                .where(InterviewSession.id == cached.id)
                .values(retention_version=1)
            )
            await writer.execute(
                update(SessionRecording)
                .where(SessionRecording.id == "retained-attempt")
                .values(audio_retention_state="deleted")
            )
            await writer.commit()
        repository = ConversationalSessionRepository(reader)
        assert not await repository.export_versions_match(cached.id, 3, 0)
        snapshot = await repository.load_export_snapshot(
            cached.id,
            ReportExportRequest(
                format="json",
                expected_activity_version=3,
                expected_retention_version=1,
                contract_version="coach_report_export_v1",
            ),
        )
        assert snapshot is not None
        assert snapshot.retention_version == 1
        assert snapshot.retention_summary["attempts"][0]["audio_state"] == "deleted"


async def seed_export_report(factory, *, consent=True):
    from app.models.coach_session import CoachSessionEvidenceRecord
    from app.services.coach_conversational_report import build_conversational_report
    from test_coach_report_analytics import seed_populated_report

    await seed_populated_report(factory)
    async with factory() as db:
        row = await db.get(InterviewSession, "populated-report")
        row.status = row.conversation_state = "completed"
        row.session_plan_json = {"evidence_selection": {
            "application_cv": "current_if_no_approved" if consent else "approved_only",
            "draft_evidence_consent": consent,
        }}
        for evidence_id, approval, text in (
            ("selected-unapproved", "candidate_selected_unapproved", "UNAPPROVED-SOURCE-CANARY"),
            ("selected-draft", "draft", "DRAFT-SOURCE-CANARY"),
            ("unused-approved", "approved", "UNRELATED-SOURCE-CANARY"),
        ):
            db.add(CoachSessionEvidenceRecord(
                session_id=row.id, evidence_id=evidence_id,
                source_type="application_cv" if approval == "candidate_selected_unapproved" else "question_bank",
                source_record_id=f"source-{evidence_id}", source_record_version="2",
                source_path="PRIVATE-EVIDENCE-PATH", snapshot_text=text,
                approval_state=approval, content_hash="c" * 64, snapshot_hash="d" * 64,
            ))
        evaluation = await db.get(InterviewAttemptEvaluation, "evaluation-root-1")
        findings = json.loads(json.dumps(evaluation.evidence_findings_json))
        findings["claims"][0]["evidence_ids"] += ["selected-unapproved", "selected-draft"]
        evaluation.evidence_findings_json = findings
        attempt = await db.get(SessionRecording, "accepted-root-1")
        attempt.self_assessment_json = {"note": "REFLECTION-SOURCE-CANARY"}
        attempt.audio_uri = "PRIVATE-AUDIO-PATH"
        await db.flush()
        snapshot = await ConversationalSessionRepository(db).load_report_input_snapshot(row.id, 7)
        row.report_json = build_conversational_report(snapshot).persisted_json()
        row.report_state = "completed"
        await db.commit()


async def export_report_http(factory, *, format_name="json", activity=7, retention=0, **flags):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.database import get_db
    from app.routers.coach_conversation import router

    app = FastAPI()
    app.include_router(router)

    async def request_db():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = request_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/api/coach/sessions/populated-report/exports", json={
            "format": format_name, "expected_activity_version": activity,
            "expected_retention_version": retention,
            "contract_version": "coach_report_export_v1", **flags,
        })


@pytest.mark.parametrize("format_name", ["json", "markdown"])
async def test_actual_export_projects_only_report_referenced_consented_evidence(coach_database, format_name):
    await seed_export_report(coach_database)
    plain = await export_report_http(coach_database, format_name=format_name)
    included = await export_report_http(coach_database, format_name=format_name, include_evidence_details=True)
    repeated = await export_report_http(coach_database, format_name=format_name, include_evidence_details=True)
    assert plain.status_code == included.status_code == repeated.status_code == 200, included.text
    assert included.content == repeated.content
    assert included.headers["etag"] == repeated.headers["etag"]
    for canary in ("Synthetic approved evidence", "UNAPPROVED-SOURCE-CANARY", "DRAFT-SOURCE-CANARY"):
        assert canary not in plain.text
        assert canary in included.text
    for canary in ("UNRELATED-SOURCE-CANARY", "PRIVATE-EVIDENCE-PATH", "PRIVATE-AUDIO-PATH"):
        assert canary not in plain.text and canary not in included.text
    assert "Candidate-selected unapproved source" in included.text
    assert "Draft source" in included.text
    assert "not independent verification" in included.text
    assert included.headers["content-disposition"] == f'attachment; filename="hatch-coach-populated-report.{"json" if format_name == "json" else "md"}"'
    assert included.headers["content-type"] == f'{"application/json" if format_name == "json" else "text/markdown"}; charset=utf-8'
    assert included.headers["cache-control"] == "no-store"
    assert included.headers["x-hatch-session-activity-version"] == "7"
    if format_name == "json":
        details = included.json()["evidence_details"]
        assert [item["evidence_id"] for item in details] == ["approved-evidence", "selected-draft", "selected-unapproved"]
        assert details[-1]["approval_state"] == "candidate_selected_unapproved"
        assert details[-1]["source_record_version"] == "2"
        assert details[-1]["attempt_ids"] == ["accepted-root-1"]


@pytest.mark.parametrize("format_name", ["json", "markdown"])
async def test_export_does_not_promote_unconsented_sources(coach_database, format_name):
    await seed_export_report(coach_database, consent=False)
    response = await export_report_http(coach_database, format_name=format_name, include_evidence_details=True)
    assert response.status_code == 200, response.text
    assert "Synthetic approved evidence" in response.text
    assert "UNAPPROVED-SOURCE-CANARY" not in response.text
    assert "DRAFT-SOURCE-CANARY" not in response.text


@pytest.mark.parametrize("state", ["active", "asking"])
async def test_export_requires_both_completed_states(coach_database, state):
    await seed_export_report(coach_database)
    async with coach_database() as db:
        row = await db.get(InterviewSession, "populated-report")
        if state == "active":
            row.status = "active"
        else:
            row.conversation_state = "asking"
        await db.commit()
    response = await export_report_http(coach_database)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "coach_report_unavailable"


@pytest.mark.parametrize("version", ["activity", "retention"])
async def test_export_version_mismatch_has_canonical_source_changed_error(coach_database, version):
    await seed_export_report(coach_database)
    response = await export_report_http(coach_database, **{version: 6 if version == "activity" else 1})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "coach_export_source_changed"


@pytest.mark.parametrize("format_name", ["json", "markdown"])
@pytest.mark.parametrize("mutation", ["activity", "retention", "hard_delete", "status"])
async def test_export_rechecks_real_concurrent_mutation_before_response(
    coach_database, monkeypatch, format_name, mutation,
):
    from sqlalchemy import update

    await seed_export_report(coach_database)
    original = ConversationalSessionRepository.load_export_snapshot

    async def capture_then_mutate(repository, session_id, request):
        snapshot = await original(repository, session_id, request)
        assert snapshot is not None
        async with coach_database() as writer:
            if mutation == "hard_delete":
                await CoachPrivacyService(ConversationalSessionRepository(writer)).claim_hard_deletion(
                    session_id, deletion_request("export-race-delete"), now=datetime.utcnow(),
                )
            else:
                values = {"activity_version": 8} if mutation == "activity" else (
                    {"retention_version": 1} if mutation == "retention" else {"status": "active"}
                )
                await writer.execute(update(InterviewSession).where(InterviewSession.id == session_id).values(**values))
            await writer.commit()
        return snapshot

    monkeypatch.setattr(ConversationalSessionRepository, "load_export_snapshot", capture_then_mutate)
    response = await export_report_http(coach_database, format_name=format_name,
        include_transcript=True, include_evidence_details=True, include_attempt_history=True)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "coach_export_source_changed"
    assert "SOURCE-CANARY" not in response.text and "Synthetic answer" not in response.text
    assert "content-disposition" not in response.headers


@pytest.mark.parametrize("format_name", ["json", "markdown"])
async def test_export_after_real_transcript_deletion_and_report_rebuild_excludes_sources(
    coach_database, format_name,
):
    from app.models.coach_session import InterviewTranscriptVersion
    from app.schemas.coach_conversation import ConversationCommandRequest
    from app.services.coach_conversation_commands import ConversationCommandService
    from app.services.coach_conversational_report import build_conversational_report
    from test_coach_report_dispatch import await_terminal

    await seed_export_report(coach_database)
    canary = "DELETED-TRANSCRIPT-CANARY"
    async with coach_database() as db:
        attempt = await db.get(SessionRecording, "accepted-root-1")
        attempt.transcript = canary
        transcript = await db.get(InterviewTranscriptVersion, attempt.current_transcript_version_id)
        transcript.transcript = canary
        evaluation = await db.get(InterviewAttemptEvaluation, attempt.current_evaluation_version_id)
        findings = json.loads(json.dumps(evaluation.evidence_findings_json))
        findings["claims"][0].update(claim_text=canary, transcript_end=len(canary))
        evaluation.evidence_findings_json = findings
        await db.flush()
        row = await db.get(InterviewSession, "populated-report")
        source = await ConversationalSessionRepository(db).load_report_input_snapshot(row.id, 7)
        row.report_json = build_conversational_report(source).persisted_json()
        await db.commit()
    before = await export_report_http(coach_database, format_name=format_name,
        include_transcript=True, include_evidence_details=True)
    assert before.status_code == 200
    assert canary in before.text and "UNAPPROVED-SOURCE-CANARY" in before.text
    async with coach_database() as db:
        row = await db.get(InterviewSession, "populated-report")
        result = await ConversationCommandService(db).execute(user_id="local", session_id=row.id,
            request=ConversationCommandRequest.model_validate({
                "command_id": "delete-export-transcript", "command_type": "delete_transcript",
                "expected_state_version": row.state_version,
                "payload": {"attempt_id": "accepted-root-1"},
                "contract_version": "coach_conversation_command_v1",
            }))
        assert result.async_job_id is not None
    row, job = await await_terminal(coach_database, result.async_job_id)
    assert job.status == "done" and row.report_state == "completed"
    after = await export_report_http(coach_database, format_name=format_name,
        activity=row.activity_version, retention=row.retention_version,
        include_transcript=True, include_evidence_details=True, include_attempt_history=True)
    assert after.status_code == 200, after.text
    for forbidden in (canary, "UNAPPROVED-SOURCE-CANARY", "DRAFT-SOURCE-CANARY", "REFLECTION-SOURCE-CANARY"):
        assert forbidden not in after.text
    assert "Synthetic approved evidence" in after.text
    async with coach_database() as db:
        attempt = await db.get(SessionRecording, "accepted-root-1")
        assert attempt.transcript is None and attempt.attempt_state == "deleted"


@pytest.mark.parametrize("invalid_source", ["foreign_evaluation", "source_deleted", "stale_span", "deleted_attempt"])
async def test_export_evidence_ignores_no_longer_current_contributors(coach_database, invalid_source):
    from app.models.coach_session import SessionQuestion, InterviewTranscriptVersion

    await seed_export_report(coach_database)
    async with coach_database() as db:
        attempt = await db.get(SessionRecording, "accepted-root-1")
        if invalid_source == "foreign_evaluation":
            attempt.current_evaluation_version_id = "evaluation-root-2"
        elif invalid_source == "source_deleted":
            question = await db.get(SessionQuestion, "root-1")
            question.source_deleted = True
        elif invalid_source == "stale_span":
            transcript = await db.get(InterviewTranscriptVersion, attempt.current_transcript_version_id)
            transcript.transcript = "A different current answer"
        else:
            attempt.attempt_state = "deleted"
            # Residual content must not be exported even in a corrupt deleted row.
            attempt.transcript = "DELETED-RESIDUAL-CANARY"
        await db.commit()
    response = await export_report_http(coach_database, include_evidence_details=True, include_transcript=True)
    assert response.status_code == 200, response.text
    for forbidden in ("UNAPPROVED-SOURCE-CANARY", "DRAFT-SOURCE-CANARY", "DELETED-RESIDUAL-CANARY"):
        assert forbidden not in response.text
    assert "Synthetic approved evidence" in response.text


async def test_export_snapshot_is_one_statement_and_creates_no_artifact(coach_database, tmp_path):
    from sqlalchemy import event, select, func

    await seed_export_report(coach_database)
    statements = []
    async with coach_database() as db:
        engine = db.bind.sync_engine
        def capture(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        event.listen(engine, "before_cursor_execute", capture)
        try:
            snapshot = await ConversationalSessionRepository(db).load_export_snapshot("populated-report", ReportExportRequest(
                format="json", expected_activity_version=7, expected_retention_version=0,
                include_transcript=True, include_evidence_details=True, include_attempt_history=True,
                contract_version="coach_report_export_v1",
            ))
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        assert snapshot is not None
        assert len(statements) == 1
        before = await db.scalar(select(func.count()).select_from(AsyncJob))
    for _ in range(2):
        assert (await export_report_http(coach_database)).status_code == 200
    async with coach_database() as db:
        assert await db.scalar(select(func.count()).select_from(AsyncJob)) == before
    assert not list(tmp_path.rglob("*.md")) and not list(tmp_path.rglob("*.json"))


def synthetic_session(**values):
    return InterviewSession(
        company_name="Synthetic Ltd",
        role_title="Engineer",
        config={},
        experience_version="conversational_v1",
        status="active",
        conversation_state="asking",
        compatibility_key="synthetic-key",
        **values,
    )


def deletion_request(command_id="delete-1"):
    return HardDeletionCommandRequest(
        command_id=command_id,
        confirmation="DELETE",
        contract_version="coach_session_hard_delete_v1",
    )


@pytest.mark.parametrize("state", ["deleting", "failed"])
async def test_hidden_deletion_state_is_excluded_from_normal_reads(
    coach_database, state
):
    async with coach_database() as db:
        row = synthetic_session(id="hidden-session", deletion_state=state)
        legacy = InterviewSession(
            id="legacy-session", company_name="Synthetic", role_title="Engineer"
        )
        db.add_all([row, legacy])
        await db.commit()
        repository = SessionRepository(db)
        assert await repository.get_session(row.id) is None
        assert row.id not in {item.id for item in await repository.list_sessions()}
        assert await repository.get_session(legacy.id) is not None
        with pytest.raises(HTTPException) as missing:
            await CoachService().get_session(row.id, db)
        assert missing.value.status_code == 404
        with pytest.raises(CoachLiveViewError):
            await CoachLiveViewService(db).get_live_view(
                user_id="local", session_id=row.id
            )
        assert (await get_conversational_report(row.id, db)).status_code == 409
        assert (await get_conversational_diagnostics(row.id, db)).status_code == 409
        exported = await export_conversational_report(
            row.id,
            ReportExportRequest(
                format="json",
                expected_activity_version=0,
                expected_retention_version=0,
                contract_version="coach_report_export_v1",
            ),
            db,
        )
        assert exported.status_code == 409
        assert (
            await ConversationalSessionRepository(db).load_progress_snapshots(
                ProgressSelector(mode="exact", compatibility_key="synthetic-key")
            )
            == []
        )


async def test_deletion_claim_fences_previous_jobs_with_a_bounded_lease(coach_database):
    now = datetime.utcnow()
    async with coach_database() as db:
        jobs = [
            AsyncJob(id=f"old-{kind}", type=kind, status="pending")
            for kind in ("setup", "attempt", "report", "cleanup", "evaluation")
        ]
        row = synthetic_session(
            id="claimed-session",
            setup_generation=3,
            setup_job_id=jobs[0].id,
            setup_claim_token="old-setup-token",
            setup_claimed_at=now,
            setup_claim_expires_at=now + timedelta(minutes=5),
            report_job_id=jobs[2].id,
        )
        db.add_all([row, *jobs])
        await db.flush()
        attempt = SessionRecording(
            id="pending-attempt",
            session_id=row.id,
            recording_type="text",
            attempt_state="pending_processing",
            processing_generation=4,
            async_job_id=jobs[1].id,
        )
        db.add(attempt)
        await db.flush()
        evaluation = InterviewAttemptEvaluation(
            id="pending-evaluation",
            recording_id=attempt.id,
            version_number=1,
            state="pending",
            async_job_id=jobs[4].id,
            evaluation_contract_version="coach_rubric_v1",
            evidence_contract_version="coach_evidence_grounding_v1",
            follow_up_contract_version="coach_follow_up_v1",
        )
        db.add(evaluation)
        await db.flush()
        db.add(
            InterviewAttemptStage(
                recording_id=attempt.id,
                evaluation_version_id=evaluation.id,
                stage_name="audio_cleanup",
                stage_state="pending",
                job_id=jobs[3].id,
            )
        )
        await db.commit()
        claim = await CoachPrivacyService(
            ConversationalSessionRepository(db)
        ).claim_hard_deletion(
            row.id,
            deletion_request(),
            now=now,
        )
        await db.commit()
        await db.refresh(row)
        await db.refresh(attempt)
        assert row.setup_generation == 4
        assert row.setup_job_id is None
        assert row.setup_claim_token is None
        assert row.setup_claimed_at is None
        assert row.setup_claim_expires_at is None
        assert row.report_job_id is None
        assert attempt.processing_generation == 5
        assert attempt.async_job_id is None
        assert row.deletion_started_at == now
        assert row.deletion_claim_expires_at == now + timedelta(
            seconds=settings.HATCH_COACH_TIMEOUT_CONVERSATIONAL_JOB_SECONDS
        )
        for job in jobs:
            await db.refresh(job)
            assert job.status == "cancelled"
        duplicate = await CoachPrivacyService(
            ConversationalSessionRepository(db)
        ).claim_hard_deletion(
            row.id,
            deletion_request(),
            now=now,
        )
        assert duplicate == claim
        with pytest.raises(ConversationalRepositoryError):
            await CoachPrivacyService(
                ConversationalSessionRepository(db)
            ).claim_hard_deletion(
                row.id,
                deletion_request("delete-2"),
                now=now,
            )
        await db.rollback()


async def test_deletion_scrubs_detached_historical_report_job_content(coach_database):
    async with coach_database() as db:
        row = synthetic_session(id="historical-report")
        owned = AsyncJob(
            id="detached-owned-report",
            type="coach_conversational_report",
            status="done",
            result_json=json.dumps(
                {"session_id": row.id, "candidate_reflection": "PRIVATE-REPORT-CANARY"}
            ),
        )
        foreign = AsyncJob(
            id="detached-foreign-report",
            type="coach_conversational_report",
            status="done",
            result_json=json.dumps(
                {
                    "session_id": "other-session",
                    "candidate_reflection": "FOREIGN-REPORT-CANARY",
                }
            ),
        )
        malformed = AsyncJob(
            id="malformed-report",
            type="coach_conversational_report",
            status="failed",
            result_json="not-json",
        )
        db.add_all([row, owned, foreign, malformed])
        await db.commit()
        await CoachPrivacyService(
            ConversationalSessionRepository(db)
        ).claim_hard_deletion(
            row.id,
            deletion_request(),
            now=datetime.utcnow(),
        )
        await db.commit()
        await db.refresh(owned)
        await db.refresh(foreign)
        await db.refresh(malformed)
        assert owned.result_json is None
        assert "FOREIGN-REPORT-CANARY" in foreign.result_json
        assert malformed.result_json == "not-json"


async def test_two_request_sessions_cannot_replace_a_live_deletion_claim(
    coach_database,
):
    async with coach_database() as db:
        db.add(synthetic_session(id="concurrent-deletion"))
        await db.commit()

    async def claim(command_id):
        async with coach_database() as db:
            try:
                result = await CoachPrivacyService(
                    ConversationalSessionRepository(db)
                ).claim_hard_deletion(
                    "concurrent-deletion",
                    deletion_request(command_id),
                    now=datetime.utcnow(),
                )
                await db.commit()
                return result.command_id
            except ConversationalRepositoryError:
                await db.rollback()
                return None

    winners = await asyncio.gather(claim("concurrent-1"), claim("concurrent-2"))
    assert sum(value is not None for value in winners) == 1
    async with coach_database() as db:
        row = await db.get(InterviewSession, "concurrent-deletion")
        assert row.deletion_generation == 1
        assert row.deletion_command_id in winners


async def test_concurrent_identical_deletion_replays_share_one_job(coach_database):
    async with coach_database() as db:
        db.add(synthetic_session(id="duplicate-deletion"))
        await db.commit()

    async def claim():
        async with coach_database() as db:
            result = await CoachPrivacyService(
                ConversationalSessionRepository(db)
            ).claim_hard_deletion(
                "duplicate-deletion",
                deletion_request(),
                now=datetime.utcnow(),
            )
            await db.commit()
            return result

    first, second = await asyncio.gather(claim(), claim())
    assert first == second
    async with coach_database() as db:
        from sqlalchemy import select

        jobs = list((await db.scalars(select(AsyncJob))).all())
        assert len(jobs) == 1


async def test_conversational_deletion_does_not_claim_a_legacy_session(coach_database):
    async with coach_database() as db:
        row = InterviewSession(
            id="legacy-privacy", company_name="Synthetic", role_title="Engineer"
        )
        db.add(row)
        await db.commit()
        with pytest.raises(ConversationalRepositoryError):
            await CoachPrivacyService(
                ConversationalSessionRepository(db)
            ).claim_hard_deletion(
                row.id,
                deletion_request(),
                now=datetime.utcnow(),
            )
        await db.rollback()
        assert (
            await db.get(InterviewSession, "legacy-privacy")
        ).deletion_state == "not_requested"


async def test_application_history_and_legacy_chain_hide_deleting_sessions(
    coach_database,
):
    from app.models.application import Application
    from app.routers.coach import get_application_progress

    async with coach_database() as db:
        db.add(Application(id="synthetic-history"))
        await db.flush()
        parent = InterviewSession(
            id="visible-parent",
            company_name="Synthetic",
            role_title="Engineer",
            application_id="synthetic-history",
        )
        db.add(parent)
        await db.flush()
        db.add(
            synthetic_session(
                id="hidden-child",
                deletion_state="deleting",
                parent_session_id=parent.id,
                application_id="synthetic-history",
            )
        )
        await db.commit()
        assert [
            row.id for row in await get_application_progress("synthetic-history", db)
        ] == [parent.id]
        chain = await SessionRepository(db).get_progress_trend(parent.id)
        assert [row["session_id"] for row in chain] == [parent.id]
