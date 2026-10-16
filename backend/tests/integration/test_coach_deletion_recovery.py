"""Real deletion dispatch, fencing, receipt and restart recovery outcomes."""

import asyncio
import hashlib
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.config import settings
from app.models.async_job import AsyncJob
from app.models.coach_session import (
    CoachSessionDeletionResult,
    InterviewSession,
    SessionRecording,
    SessionQuestion,
    InterviewTranscriptVersion,
    InterviewAttemptEvaluation,
    InterviewAttemptStage,
    InterviewAttemptUpload,
    InterviewSessionEvent,
    ConversationCommandResultRecord,
    CoachSessionEvidenceRecord,
)
from app.repositories.conversational_session_repository import (
    ConversationalRepositoryError,
    ConversationalSessionRepository,
)
from app.routers.coach_conversation import request_hard_deletion
from app.services.coach_privacy import CoachPrivacyService, expire_deletion_receipts
from app.services.coach_reconciliation import reconcile_conversational_session
from app.services.coach_reconciliation import reconcile_stale_coach_state
from app.services.coach_privacy_queue import (
    _process_hard_deletion,
    install_deletion_receipt_retention,
    purge_deletion_receipts,
)
from test_coach_report_privacy_flow import deletion_request, synthetic_session


async def test_startup_selector_discovers_hidden_expired_deletion(coach_database):
    claim = await claimed_session(coach_database)
    async with coach_database() as db:
        row = await db.get(InterviewSession, claim.session_id)
        row.deletion_claim_expires_at = datetime.utcnow() - timedelta(minutes=1)
        await db.commit()
    assert await reconcile_stale_coach_state() == 1
    assert await reconcile_stale_coach_state() == 0
    async with coach_database() as db:
        row = await db.get(InterviewSession, claim.session_id)
        assert row.deletion_state == "failed"
        assert row.deletion_error_code == "coach_deletion_claim_expired"


async def test_finalization_physically_cascades_every_owned_content_table(
    coach_database,
):
    claim = await claimed_session(coach_database)
    async with coach_database() as db:
        db.add(
            SessionQuestion(
                id="owned-question",
                session_id=claim.session_id,
                question_num=1,
                text="Synthetic question",
                category="behavioural",
                order_in_session=1,
            )
        )
        await db.flush()
        db.add(
            SessionRecording(
                id="owned-recording",
                session_id=claim.session_id,
                question_id="owned-question",
                recording_type="text",
                attempt_state="completed",
                transcript="Synthetic transcript",
            )
        )
        await db.flush()
        db.add(
            InterviewTranscriptVersion(
                id="owned-transcript",
                recording_id="owned-recording",
                version_number=1,
                transcript="Synthetic transcript",
                source="candidate_text",
                created_by="candidate",
            )
        )
        await db.flush()
        db.add(
            InterviewAttemptEvaluation(
                id="owned-evaluation",
                recording_id="owned-recording",
                transcript_version_id="owned-transcript",
                version_number=1,
                state="completed",
                rubric_json={"synthetic": "content"},
                evaluation_contract_version="coach_conversational_rubric_v1",
                evidence_contract_version="coach_evidence_grounding_v1",
                follow_up_contract_version="coach_follow_up_v1",
            )
        )
        await db.flush()
        db.add_all(
            [
                InterviewAttemptStage(
                    recording_id="owned-recording",
                    evaluation_version_id="owned-evaluation",
                    stage_name="content_evaluation",
                    stage_state="completed",
                ),
                InterviewAttemptUpload(
                    attempt_id="owned-recording",
                    upload_id="deleted-upload",
                    request_hash="a" * 64,
                    content_sha256="a" * 64,
                    byte_size=1,
                    mime_type="audio/webm",
                    storage_uri=str(
                        Path(settings.HATCH_COACH_MEDIA_ROOT)
                        / claim.session_id
                        / "gone.webm"
                    ),
                    result_state="deleted",
                ),
                InterviewSessionEvent(
                    session_id=claim.session_id,
                    sequence_number=1,
                    event_type="session_started",
                    state_version=0,
                    actor_type="candidate",
                    payload_json={},
                ),
                ConversationCommandResultRecord(
                    session_id=claim.session_id,
                    command_id="old-command",
                    command_type="start",
                    request_hash="a" * 64,
                    expected_state_version=0,
                    result_state="completed",
                ),
                CoachSessionEvidenceRecord(
                    session_id=claim.session_id,
                    evidence_id="evidence-1",
                    source_type="synthetic",
                    source_record_id="synthetic-source",
                    source_record_version="1",
                    source_path="synthetic",
                    snapshot_text="Synthetic evidence",
                    approval_state="approved",
                    content_hash="a" * 64,
                    snapshot_hash="b" * 64,
                ),
            ]
        )
        media_dir = Path(settings.HATCH_COACH_MEDIA_ROOT) / claim.session_id
        media_dir.mkdir(parents=True)
        await db.commit()
        result = await ConversationalSessionRepository(db).finalise_hard_deletion(
            claim, datetime.utcnow()
        )
        await db.commit()
        assert result.result_state == "completed"
        for model in (
            SessionQuestion,
            SessionRecording,
            InterviewTranscriptVersion,
            InterviewAttemptEvaluation,
            InterviewAttemptStage,
            InterviewAttemptUpload,
            InterviewSessionEvent,
            ConversationCommandResultRecord,
            CoachSessionEvidenceRecord,
        ):
            assert list((await db.scalars(select(model))).all()) == []
        assert (
            len(list((await db.scalars(select(CoachSessionDeletionResult))).all())) == 1
        )


async def test_job_poll_reconciles_a_lost_deletion_dispatch(coach_database):
    from app.services.coach_reconciliation import reconcile_job

    claim = await claimed_session(coach_database)
    async with coach_database() as db:
        row = await db.get(InterviewSession, claim.session_id)
        row.deletion_claim_expires_at = datetime.utcnow() - timedelta(minutes=1)
        await db.commit()
        assert await reconcile_job(db, claim.job_id) == 1
        assert await reconcile_job(db, claim.job_id) == 0


async def claimed_session(factory):
    async with factory() as db:
        db.add(synthetic_session(id="delete-session"))
        await db.commit()
        claim = await CoachPrivacyService(
            ConversationalSessionRepository(db)
        ).claim_hard_deletion(
            "delete-session",
            deletion_request(),
            now=datetime.utcnow(),
        )
        await db.commit()
        return claim


async def test_real_deletion_route_completes_after_request_session_closes(
    coach_database,
):
    async with coach_database() as db:
        db.add(synthetic_session(id="delete-session"))
        await db.commit()
        response = await request_hard_deletion("delete-session", deletion_request(), db)
        assert response.result_state == "processing"
    deadline = asyncio.get_running_loop().time() + 3
    while True:
        async with coach_database() as db:
            receipt = await db.scalar(select(CoachSessionDeletionResult))
            if receipt.result_state != "processing":
                assert receipt.result_state == "completed"
                assert await db.get(InterviewSession, "delete-session") is None
                assert receipt.expires_at == receipt.completed_at + timedelta(
                    days=settings.HATCH_COACH_DELETION_RECEIPT_DAYS
                )
                replay = await request_hard_deletion(
                    "delete-session", deletion_request(), db
                )
                assert replay.result_state == "completed"
                break
        assert asyncio.get_running_loop().time() < deadline, (
            "Committed deletion was never executed"
        )
        await asyncio.sleep(0.02)


@pytest.mark.parametrize(
    "field,value",
    [
        ("deletion_generation", 2),
        ("job_id", "foreign-job"),
        ("command_id", "foreign-command"),
        ("claim_token", "foreign-token"),
    ],
)
async def test_stale_success_and_failure_finalizers_mutate_nothing(
    coach_database, field, value
):
    claim = await claimed_session(coach_database)
    stale = replace(claim, **{field: value})
    async with coach_database() as db:
        repository = ConversationalSessionRepository(db)
        with pytest.raises(ConversationalRepositoryError):
            await repository.finalise_hard_deletion(stale, datetime.utcnow())
        await db.rollback()
        with pytest.raises(ConversationalRepositoryError):
            await repository.fail_hard_deletion(
                stale, "coach_session_deletion_failed", datetime.utcnow()
            )
        await db.rollback()
        row = await db.get(InterviewSession, claim.session_id)
        receipt = await db.scalar(select(CoachSessionDeletionResult))
        assert row.deletion_state == "deleting"
        assert receipt.result_state == "processing"
        assert (await db.get(AsyncJob, claim.job_id)).status == "pending"


async def test_expired_deletion_is_reconciled_once_and_retry_uses_new_command(
    coach_database,
):
    claim = await claimed_session(coach_database)
    future = datetime.utcnow() + timedelta(hours=1)
    async with coach_database() as db:
        assert (
            await reconcile_conversational_session(db, claim.session_id, now=future)
            == 1
        )
        assert (
            await reconcile_conversational_session(db, claim.session_id, now=future)
            == 0
        )
        row = await db.get(InterviewSession, claim.session_id)
        assert row.deletion_state == "failed"
        assert row.deletion_job_id is None
        assert row.deletion_command_id is None
        assert row.deletion_claim_token is None
        assert row.deletion_claim_expires_at is None
        assert row.deletion_started_at is None
        service = CoachPrivacyService(ConversationalSessionRepository(db))
        replay = await service.claim_hard_deletion(
            claim.session_id, deletion_request(), now=future
        )
        assert replay.result_state == "failed"
        assert replay.error_code == "coach_deletion_claim_expired"
        receipt = await db.scalar(select(CoachSessionDeletionResult))
        assert receipt.expires_at == future + timedelta(
            days=settings.HATCH_COACH_DELETION_RECEIPT_DAYS
        )
        replacement = await service.claim_hard_deletion(
            claim.session_id, deletion_request("retry-delete"), now=future
        )
        assert replacement.deletion_generation == 2
        await db.commit()


async def test_expired_claim_cannot_delete_the_session(coach_database):
    claim = await claimed_session(coach_database)
    async with coach_database() as db:
        with pytest.raises(ConversationalRepositoryError):
            await ConversationalSessionRepository(db).finalise_hard_deletion(
                claim,
                datetime.utcnow() + timedelta(hours=1),
            )
        await db.rollback()
        assert await db.get(InterviewSession, claim.session_id) is not None


async def test_cleanup_preserves_processing_receipts(coach_database):
    await claimed_session(coach_database)
    future = datetime.utcnow() + timedelta(days=100)
    async with coach_database() as db:
        assert (
            await expire_deletion_receipts(
                ConversationalSessionRepository(db), now=future
            )
            == 0
        )
        assert await db.scalar(select(CoachSessionDeletionResult)) is not None


async def test_missing_owned_media_is_idempotent_success(coach_database):
    claim = await claimed_session(coach_database)
    media_dir = Path(settings.HATCH_COACH_MEDIA_ROOT) / claim.session_id
    media_dir.mkdir(parents=True)
    async with coach_database() as db:
        db.add(
            SessionRecording(
                id="gone-audio",
                session_id=claim.session_id,
                recording_type="audio",
                attempt_state="completed",
                audio_uri=str(media_dir / "gone.webm"),
                audio_content_hash="a" * 64,
                audio_retention_state="retained",
            )
        )
        await db.commit()
        result = await ConversationalSessionRepository(db).finalise_hard_deletion(
            claim, datetime.utcnow()
        )
        await db.commit()
        assert result.result_state == "completed"
        assert await db.get(SessionRecording, "gone-audio") is None


async def test_service_does_not_hide_a_failed_database_transaction(coach_database):
    claim = await claimed_session(coach_database)
    async with coach_database() as db:
        await db.execute(
            text("""CREATE TRIGGER refuse_session_delete
            BEFORE DELETE ON interview_sessions
            BEGIN SELECT RAISE(ABORT, 'synthetic-delete-fault'); END""")
        )
        await db.commit()
        with pytest.raises(DBAPIError):
            await CoachPrivacyService(
                ConversationalSessionRepository(db)
            ).run_hard_deletion(
                claim,
                now=datetime.utcnow(),
            )
        await db.rollback()
        assert (await db.get(AsyncJob, claim.job_id)).status == "pending"
        assert (
            await db.scalar(select(CoachSessionDeletionResult))
        ).result_state == "processing"


async def test_worker_rolls_back_sql_failure_before_publishing_safe_failure(
    coach_database,
    caplog,
):
    claim = await claimed_session(coach_database)
    async with coach_database() as db:
        await db.execute(
            text("""CREATE TRIGGER refuse_worker_delete
            BEFORE DELETE ON interview_sessions
            BEGIN SELECT RAISE(ABORT, 'PRIVATE-SQL-CANARY'); END""")
        )
        await db.commit()
    with caplog.at_level("INFO"):
        await _process_hard_deletion(claim)
    assert "PRIVATE-SQL-CANARY" not in caplog.text
    async with coach_database() as db:
        row = await db.get(InterviewSession, claim.session_id)
        job = await db.get(AsyncJob, claim.job_id)
        receipt = await db.scalar(select(CoachSessionDeletionResult))
        assert row.deletion_state == "failed"
        assert job.status == "failed"
        assert receipt.result_state == "failed"
        assert job.error == receipt.error_code == "coach_session_deletion_failed"


@pytest.mark.parametrize("kind", ["foreign_session", "outside_root", "symlink"])
async def test_deletion_never_removes_foreign_or_symlink_media(
    coach_database,
    tmp_path,
    kind,
    caplog,
):
    claim = await claimed_session(coach_database)
    content = b"PRIVATE-MEDIA-CANARY"
    media_root = Path(settings.HATCH_COACH_MEDIA_ROOT)
    if kind == "foreign_session":
        protected = media_root / "other-session" / "protected.webm"
    else:
        protected = tmp_path / "outside" / "protected.webm"
    protected.parent.mkdir(parents=True)
    protected.write_bytes(content)
    uri = protected
    if kind == "symlink":
        uri = media_root / claim.session_id / "linked.webm"
        uri.parent.mkdir(parents=True)
        uri.symlink_to(protected)
    async with coach_database() as db:
        db.add(
            SessionRecording(
                id="unsafe-media",
                session_id=claim.session_id,
                recording_type="audio",
                attempt_state="completed",
                audio_uri=str(uri),
                audio_content_hash=hashlib.sha256(content).hexdigest(),
                audio_retention_state="retained",
            )
        )
        await db.commit()
    with caplog.at_level("INFO"):
        await _process_hard_deletion(claim)
    assert protected.read_bytes() == content
    assert str(uri) not in caplog.text
    assert "PRIVATE-MEDIA-CANARY" not in caplog.text
    async with coach_database() as db:
        assert (
            await db.get(InterviewSession, claim.session_id)
        ).deletion_state == "failed"
        assert (
            await db.scalar(select(CoachSessionDeletionResult))
        ).error_code == "coach_session_deletion_failed"


@pytest.mark.parametrize("mismatch", [False, True])
async def test_worker_removes_only_hash_verified_owned_media(coach_database, mismatch):
    claim = await claimed_session(coach_database)
    media_dir = Path(settings.HATCH_COACH_MEDIA_ROOT) / claim.session_id
    media_dir.mkdir(parents=True)
    media = media_dir / "answer.webm"
    media.write_bytes(b"synthetic audio fixture")
    expected_hash = (
        "a" * 64 if mismatch else hashlib.sha256(b"synthetic audio fixture").hexdigest()
    )
    async with coach_database() as db:
        db.add(
            SessionRecording(
                id="owned-audio",
                session_id=claim.session_id,
                recording_type="audio",
                attempt_state="completed",
                audio_uri=str(media),
                audio_content_hash=expected_hash,
                audio_retention_state="retained",
            )
        )
        await db.commit()
    await _process_hard_deletion(claim)
    async with coach_database() as db:
        receipt = await db.scalar(select(CoachSessionDeletionResult))
        assert receipt.result_state == ("failed" if mismatch else "completed")
        assert media.exists() == mismatch
        assert (
            await db.get(InterviewSession, claim.session_id) is not None
        ) == mismatch
        assert (await db.get(AsyncJob, claim.job_id)).status == (
            "failed" if mismatch else "done"
        )
        if mismatch:
            assert receipt.error_code == "coach_session_deletion_failed"
            assert receipt.expires_at == receipt.completed_at + timedelta(
                days=settings.HATCH_COACH_DELETION_RECEIPT_DAYS
            )


async def test_daily_receipt_cleanup_is_registered_and_preserves_live_claims(
    coach_database,
):
    claim = await claimed_session(coach_database)
    async with coach_database() as db:
        db.add(
            CoachSessionDeletionResult(
                session_key_hash="a" * 64,
                command_id="expired-receipt",
                request_hash="b" * 64,
                result_state="completed",
                completed_at=datetime.utcnow() - timedelta(days=40),
                expires_at=datetime.utcnow() - timedelta(days=10),
            )
        )
        await db.commit()

    class Scheduler:
        jobs = []

        def add_job(self, function, trigger, **kwargs):
            self.jobs.append((function, trigger, kwargs))

    scheduler = Scheduler()
    await install_deletion_receipt_retention(scheduler, coach_database)
    assert len(scheduler.jobs) == 2
    function, trigger, options = scheduler.jobs[0]
    recovery, recovery_trigger, recovery_options = scheduler.jobs[1]
    assert recovery_trigger == "interval"
    assert recovery_options["seconds"] == 60
    assert recovery_options["max_instances"] == 1
    assert recovery_options["coalesce"] is True
    assert trigger == "interval"
    assert options["days"] == 1
    assert options["replace_existing"] is True
    assert options["max_instances"] == 1
    assert options["coalesce"] is True
    await function(**options["kwargs"])
    async with coach_database() as db:
        receipts = list((await db.scalars(select(CoachSessionDeletionResult))).all())
        assert len(receipts) == 1
        assert receipts[0].command_id == claim.command_id
    assert (
        await purge_deletion_receipts(
            coach_database, now=datetime.utcnow() + timedelta(days=100)
        )
        == 0
    )
    async with coach_database() as db:
        row = await db.get(InterviewSession, claim.session_id)
        row.deletion_claim_expires_at = datetime.utcnow() - timedelta(minutes=1)
        await db.commit()
    assert await recovery(**recovery_options["kwargs"]) == 1
    assert await recovery(**recovery_options["kwargs"]) == 0
