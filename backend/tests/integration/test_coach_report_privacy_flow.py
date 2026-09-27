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
                ProgressSelector(mode="filtered", compatibility_key="synthetic-key")
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
