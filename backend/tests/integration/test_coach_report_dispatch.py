"""Real post-commit report execution and durable recovery, using synthetic data."""

import asyncio
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select, text

from app.models.async_job import AsyncJob
from app.models.coach_session import InterviewSession, InterviewSessionEvent
from app.repositories.conversational_session_repository import (
    ConversationalSessionRepository,
)
from app.schemas.coach_conversation import ConversationCommandRequest
from app.services.coach_conversation_commands import ConversationCommandService
from app.services.coach_conversational_report import (
    build_conversational_report,
    ReportBuildClaim,
)
from app.services.coach_reconciliation import (
    reconcile_conversational_session,
    reconcile_stale_coach_state,
)
from test_coach_report_analytics import seed_populated_report
from test_coach_report_privacy_flow import read_report_http, deletion_request


async def prepare_command(factory, reason):
    await seed_populated_report(factory)
    async with factory() as db:
        row = await db.get(InterviewSession, "populated-report")
        row.event_version = 3
        if reason == "manual_retry":
            row.conversation_state = "recoverable_error"
            row.recoverable_error_scope = "initial_report"
            row.recoverable_error_code = "coach_report_conversational_snapshot_stale"
            row.report_state = "failed"
            row.report_build_reason = "initial_completion"
            kind, payload = "retry_report", {}
        elif reason == "initial_completion":
            kind, payload = (
                "end_session",
                {"unaccepted_attempt_action": "not_applicable"},
            )
        else:
            row.status = "completed"
            row.conversation_state = "completed"
            row.report_state = "completed"
            snapshot = await ConversationalSessionRepository(
                db
            ).load_report_input_snapshot(row.id, 7)
            row.report_json = build_conversational_report(snapshot).persisted_json()
            if reason == "transcript_deletion_rebuild":
                kind, payload = "delete_transcript", {"attempt_id": "accepted-root-1"}
            else:
                kind, payload = (
                    "record_self_assessment",
                    {
                        "attempt_id": "accepted-root-2",
                        "comfort_level": "high",
                        "felt_complete": True,
                        "note": "Synthetic reflection",
                    },
                )
        await db.commit()
        return ConversationCommandRequest.model_validate(
            {
                "command_id": f"report-{reason}",
                "command_type": kind,
                "expected_state_version": row.state_version,
                "payload": payload,
                "contract_version": "coach_conversation_command_v1",
            }
        )


async def await_terminal(factory, job_id, *, timeout=4):
    async with asyncio.timeout(timeout):
        while True:
            async with factory() as db:
                job = await db.get(AsyncJob, job_id)
                row = await db.get(InterviewSession, "populated-report")
                if job.status in {"done", "failed", "cancelled"}:
                    return row, job
            await asyncio.sleep(0.02)


@pytest.mark.parametrize(
    "reason",
    [
        "initial_completion",
        "manual_retry",
        "transcript_deletion_rebuild",
        "reflection_update_rebuild",
    ],
)
async def test_commands_really_dispatch_reports_after_request_session_closes(
    coach_database, reason
):
    request = await prepare_command(coach_database, reason)
    async with coach_database() as db:
        result = await ConversationCommandService(db).execute(
            user_id="local", session_id="populated-report", request=request
        )
        job_id = result.async_job_id
        assert job_id is not None
    row, job = await await_terminal(coach_database, job_id)
    assert job.status == "done"
    assert row.report_state == "completed"
    assert row.report_job_id is None
    assert row.status == row.conversation_state == "completed"
    assert row.report_build_reason == reason
    response = await read_report_http(coach_database, row.id)
    assert response.status_code == 200, response.text
    if reason == "transcript_deletion_rebuild":
        assert "accepted-root-1" not in json.dumps(
            response.json()["evidence_review_items"]
        )
    if reason == "reflection_update_rebuild":
        assert response.json()["candidate_reflection"]["note"] == "Synthetic reflection"
    async with coach_database() as db:
        job_count = await db.scalar(select(func.count()).select_from(AsyncJob))
        completion_type = (
            "report_rebuild_completed"
            if reason in {"transcript_deletion_rebuild", "reflection_update_rebuild"}
            else "report_completed"
        )
        completion_events = list(
            (
                await db.scalars(
                    select(InterviewSessionEvent).where(
                        InterviewSessionEvent.session_id == row.id,
                        InterviewSessionEvent.event_type.in_(
                            ("report_completed", "report_rebuild_completed")
                        ),
                    )
                )
            ).all()
        )
        assert len(completion_events) == 1
        assert completion_events[0].event_type == completion_type
        assert completion_events[0].actor_type == "worker"
    for _ in range(2):
        assert (await read_report_http(coach_database, row.id)).status_code == 200
    async with coach_database() as db:
        assert await db.scalar(select(func.count()).select_from(AsyncJob)) == job_count


@pytest.mark.parametrize(
    "reason",
    ["initial_completion", "transcript_deletion_rebuild", "reflection_update_rebuild"],
)
async def test_lost_dispatch_is_recovered_as_failed_without_automatic_retry(
    coach_database, reason
):
    await seed_populated_report(coach_database)
    now = datetime.utcnow()
    async with coach_database() as db:
        row = await db.get(InterviewSession, "populated-report")
        row.report_state = "building"
        row.report_build_reason = reason
        row.report_job_id = "lost-report-job"
        row.report_started_at = now - timedelta(days=1)
        row.report_contract_version = "coach_conversational_report_v1"
        row.status = "active" if reason == "initial_completion" else "completed"
        row.conversation_state = (
            "reporting" if reason == "initial_completion" else "completed"
        )
        db.add(
            AsyncJob(
                id=row.report_job_id,
                type="coach_conversational_report",
                status="pending",
                updated_at=row.report_started_at,
            )
        )
        await db.commit()
    assert await reconcile_stale_coach_state() == 1
    async with coach_database() as db:
        row = await db.get(InterviewSession, "populated-report")
        assert row.report_state == "failed"
        assert row.report_job_id is None
        assert row.report_started_at is None
        assert row.conversation_state == (
            "recoverable_error" if reason == "initial_completion" else "completed"
        )
        assert row.status == (
            "active" if reason == "initial_completion" else "completed"
        )
        assert (await db.get(AsyncJob, "lost-report-job")).status == "failed"
        failure_event = await db.scalar(
            select(InterviewSessionEvent).where(
                InterviewSessionEvent.session_id == row.id,
                InterviewSessionEvent.event_type == "report_rebuild_failed",
            )
        )
        assert failure_event.actor_type == "reconciler"
        assert await reconcile_conversational_session(db, row.id, now=now) == 0
        assert await db.scalar(select(func.count()).select_from(AsyncJob)) == 1
        retry = ConversationCommandRequest.model_validate(
            {
                "command_id": "explicit-report-retry",
                "command_type": "retry_report",
                "expected_state_version": row.state_version,
                "payload": {},
                "contract_version": "coach_conversation_command_v1",
            }
        )
        result = await ConversationCommandService(db).execute(
            user_id="local", session_id=row.id, request=retry
        )
    row, job = await await_terminal(coach_database, result.async_job_id)
    assert job.status == "done"
    assert row.status == row.conversation_state == "completed"


async def test_report_worker_rolls_back_before_fenced_failure_publication(
    coach_database, caplog
):
    from app.services.coach_report_queue import _process_conversational_report

    await seed_populated_report(coach_database)
    async with coach_database() as db:
        row = await db.get(InterviewSession, "populated-report")
        row.report_state, row.report_build_reason = "building", "initial_completion"
        row.report_job_id, row.report_started_at = "publication-job", datetime.utcnow()
        row.conversation_state = "reporting"
        db.add(
            AsyncJob(
                id=row.report_job_id,
                type="coach_conversational_report",
                status="pending",
            )
        )
        await db.commit()
        await ConversationalSessionRepository(db).persist_report_build_claim(
            row.report_job_id
        )
        await db.commit()
        await db.execute(
            text(
                "CREATE TRIGGER reject_report_publication BEFORE UPDATE OF report_json ON interview_sessions WHEN NEW.report_json IS NOT NULL BEGIN SELECT RAISE(ABORT, 'synthetic-private-publication-canary'); END"
            )
        )
        await db.commit()
    await _process_conversational_report("publication-job")
    async with coach_database() as db:
        row = await db.get(InterviewSession, "populated-report")
        job = await db.get(AsyncJob, "publication-job")
        assert row.report_state == "failed"
        assert row.report_json is None
        assert row.report_job_id is None
        assert row.recoverable_error_scope == "initial_report"
        assert job.status == "failed"
        assert job.result_json is None
        assert job.error == "coach_report_worker_failed"
        failure_event = await db.scalar(
            select(InterviewSessionEvent).where(
                InterviewSessionEvent.session_id == row.id,
                InterviewSessionEvent.event_type == "report_rebuild_failed",
            )
        )
        assert failure_event.actor_type == "worker"
        assert (
            await db.scalar(
                select(func.count())
                .select_from(InterviewSessionEvent)
                .where(InterviewSessionEvent.event_type == "report_rebuild_failed")
            )
            == 1
        )
    assert "synthetic-private-publication-canary" not in caplog.text


@pytest.mark.parametrize("fence", ["replacement_job", "activity", "deletion"])
async def test_old_report_worker_cannot_publish_or_fail_a_new_owner(
    coach_database, fence
):
    from app.services.coach_report_queue import _process_conversational_report

    await seed_populated_report(coach_database)
    claim = ReportBuildClaim("populated-report", 7, "initial_completion", "stale-job")
    async with coach_database() as db:
        row = await db.get(InterviewSession, "populated-report")
        row.report_state, row.report_build_reason = "building", "initial_completion"
        row.report_job_id, row.report_started_at = claim.job_id, datetime.utcnow()
        row.conversation_state = "reporting"
        db.add(
            AsyncJob(
                id=claim.job_id, type="coach_conversational_report", status="pending"
            )
        )
        await db.commit()
        repository = ConversationalSessionRepository(db)
        await repository.persist_report_build_claim(claim.job_id)
        await db.commit()
        snapshot = await repository.load_report_input_snapshot(row.id, 7)
        report = build_conversational_report(snapshot).persisted_json()
        if fence == "replacement_job":
            row.report_job_id = "replacement-job"
            db.add(
                AsyncJob(
                    id=row.report_job_id,
                    type="coach_conversational_report",
                    status="pending",
                )
            )
        elif fence == "activity":
            row.activity_version += 1
        else:
            await repository.claim_hard_deletion(
                row.id, deletion_request(), "a" * 64, datetime.utcnow()
            )
        await db.commit()
        assert not await repository.finalise_conversational_report(
            claim, report, "completed"
        )
        await db.commit()
        before = (
            row.report_job_id,
            row.report_state,
            row.activity_version,
            row.deletion_state,
        )
    await _process_conversational_report(claim.job_id)
    async with coach_database() as db:
        row = await db.get(InterviewSession, "populated-report")
        assert (
            row.report_job_id,
            row.report_state,
            row.activity_version,
            row.deletion_state,
        ) == before
        assert row.report_json is None


async def test_dispatch_exception_keeps_committed_command_and_later_explicit_retry(
    coach_database, monkeypatch, caplog
):
    request = await prepare_command(coach_database, "initial_completion")

    def lost_wakeup(_job_id):
        raise RuntimeError("synthetic-private-dispatch-canary")

    monkeypatch.setattr(
        "app.services.coach_conversation_commands.queue_conversational_report",
        lost_wakeup,
    )
    async with coach_database() as db:
        service = ConversationCommandService(db)
        result = await service.execute(
            user_id="local", session_id="populated-report", request=request
        )
        replay = await service.execute(
            user_id="local", session_id="populated-report", request=request
        )
        assert replay == result
        assert await db.scalar(select(func.count()).select_from(AsyncJob)) == 1
        row = await db.get(InterviewSession, "populated-report")
        assert row.report_state == "building"
        assert (await db.get(AsyncJob, result.async_job_id)).status == "pending"
        assert (
            await reconcile_conversational_session(
                db, row.id, now=datetime.utcnow() + timedelta(days=1)
            )
            == 1
        )
    assert "synthetic-private-dispatch-canary" not in caplog.text


async def test_report_recovery_handles_missing_generic_job(coach_database):
    await seed_populated_report(coach_database)
    async with coach_database() as db:
        row = await db.get(InterviewSession, "populated-report")
        row.report_state, row.report_build_reason = "building", "initial_completion"
        row.report_job_id = "missing-job"
        row.report_started_at = datetime.utcnow() - timedelta(days=1)
        row.conversation_state = "reporting"
        await db.commit()
    assert await reconcile_stale_coach_state() == 1
    async with coach_database() as db:
        row = await db.get(InterviewSession, "populated-report")
        assert row.report_state == "failed"
        assert row.report_job_id is None
        assert row.recoverable_error_scope == "initial_report"


async def test_optional_callback_and_command_replay_do_not_replace_real_report_dispatch(
    coach_database, caplog
):
    request = await prepare_command(coach_database, "initial_completion")
    notifications = []

    async def notify(job_id):
        notifications.append(job_id)
        raise RuntimeError("synthetic-private-notification-canary")

    async with coach_database() as db:
        service = ConversationCommandService(db, after_commit=notify)
        result = await service.execute(
            user_id="local", session_id="populated-report", request=request
        )
        assert (
            await service.execute(
                user_id="local", session_id="populated-report", request=request
            )
            == result
        )
    row, job = await await_terminal(coach_database, result.async_job_id)
    assert notifications == [result.async_job_id]
    assert job.status == "done"
    assert row.report_state == "completed"
    assert "synthetic-private-notification-canary" not in caplog.text


@pytest.mark.parametrize("payload", ["not-json", "[]", '{"activity_version":false}'])
async def test_corrupt_report_claim_never_builds_but_expired_shell_can_be_recovered(
    coach_database, payload
):
    from app.services.coach_report_queue import _process_conversational_report

    await seed_populated_report(coach_database)
    async with coach_database() as db:
        row = await db.get(InterviewSession, "populated-report")
        row.report_state, row.report_build_reason = "building", "initial_completion"
        row.report_job_id = "corrupt-job"
        row.report_started_at = datetime.utcnow() - timedelta(days=1)
        row.conversation_state = "reporting"
        db.add(
            AsyncJob(
                id=row.report_job_id,
                type="coach_conversational_report",
                status="pending",
                result_json=payload,
            )
        )
        await db.commit()
    await _process_conversational_report("corrupt-job")
    async with coach_database() as db:
        row = await db.get(InterviewSession, "populated-report")
        assert row.report_state == "building"
        assert row.report_json is None
    assert await reconcile_stale_coach_state() == 1
    async with coach_database() as db:
        row = await db.get(InterviewSession, "populated-report")
        assert row.report_state == "failed"
        assert row.report_job_id is None


async def test_hidden_session_cannot_create_a_new_initial_report_claim(coach_database):
    await seed_populated_report(coach_database)
    async with coach_database() as db:
        row = await db.get(InterviewSession, "populated-report")
        row.conversation_state = "reporting"
        row.report_state = "building"
        row.deletion_state = "failed"
        await db.commit()
        repository = ConversationalSessionRepository(db)
        assert (
            await repository.claim_initial_conversational_report(
                session_id=row.id,
                expected_activity_version=7,
                build_reason="initial_completion",
                job_id="forbidden-report-job",
                now=datetime.utcnow(),
            )
            is None
        )
        assert await repository.load_report_input_snapshot(row.id, 7) is None


async def test_invalid_analytical_projection_fails_before_publishing_unreadable_report(
    coach_database,
):
    from app.models.coach_session import InterviewAttemptEvaluation

    request = await prepare_command(coach_database, "initial_completion")
    async with coach_database() as db:
        evaluation = await db.get(InterviewAttemptEvaluation, "evaluation-root-1")
        evaluation.answer_level = "invalid-level"
        await db.commit()
        result = await ConversationCommandService(db).execute(
            user_id="local", session_id="populated-report", request=request
        )
    row, job = await await_terminal(coach_database, result.async_job_id)
    assert job.status == "failed"
    assert row.report_state == "failed"
    assert row.report_json is None
    assert row.report_job_id is None
    assert row.conversation_state == "recoverable_error"


@pytest.mark.parametrize(
    "code", [None, "coach_report_unavailable", "coach_audio_deletion_failed"]
)
async def test_initial_report_retry_requires_a_retryable_report_failure(
    coach_database, code
):
    from app.services.coach_conversation_commands import ConversationCommandError

    request = await prepare_command(coach_database, "manual_retry")
    async with coach_database() as db:
        row = await db.get(InterviewSession, "populated-report")
        row.recoverable_error_code = code
        await db.commit()
        with pytest.raises(ConversationCommandError):
            await ConversationCommandService(db).execute(
                user_id="local", session_id=row.id, request=request
            )
        assert await db.scalar(select(func.count()).select_from(AsyncJob)) == 0
