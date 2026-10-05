"""Exercise Coach startup recovery across actual backend process boundaries."""

import asyncio
import hashlib
from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import create_sqlite_engine
from app.models.async_job import AsyncJob
from app.models.coach_session import (
    CoachSessionDeletionResult,
    InterviewSession,
    InterviewSessionEvent,
    SessionQuestion,
    SessionRecording,
)
from app.repositories.conversational_session_repository import ConversationalSessionRepository
from app.schemas.coach import SessionFeedbackReport
from app.services.coach_privacy import CoachPrivacyService
from test_coach_report_analytics import seed_populated_report
from test_coach_report_privacy_flow import (
    deletion_request,
    seed_built_report,
    synthetic_session,
)

from coach_app_process import CoachAppProcess


@pytest.mark.asyncio
async def test_real_app_routes_conversational_report_to_versioned_reader(tmp_path):
    database_path = tmp_path / "report-route.db"
    async with CoachAppProcess(database_path, tmp_path / "media") as app_process:
        engine = create_sqlite_engine(f"sqlite+aiosqlite:///{database_path}")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            await seed_built_report(factory)
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.get(
                    f"{app_process.base_url}/api/coach/sessions/readable-report/report"
                )
            assert response.status_code == 200
            assert response.json()["contract_version"] == "coach_conversational_report_v1"
            assert response.headers["x-hatch-session-activity-version"] == "3"
            assert response.headers["cache-control"] == "no-store"
        finally:
            await engine.dispose()


@pytest.mark.asyncio
async def test_real_app_preserves_legacy_numeric_report_on_shared_url(tmp_path):
    database_path = tmp_path / "legacy-report-route.db"
    async with CoachAppProcess(database_path, tmp_path / "media") as app_process:
        engine = create_sqlite_engine(f"sqlite+aiosqlite:///{database_path}")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            expected = SessionFeedbackReport(
                session_id="legacy-report", overall_score=7.5
            ).model_dump(mode="json")
            async with factory() as db:
                db.add(
                    InterviewSession(
                        id="legacy-report",
                        company_name="Synthetic Legacy Co",
                        role_title="Engineer",
                        config={},
                        status="completed",
                        experience_version="legacy_v1",
                        report_state="completed",
                        report_json=expected,
                    )
                )
                await db.commit()
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.get(
                    f"{app_process.base_url}/api/coach/sessions/legacy-report/report"
                )
            assert response.status_code == 200
            assert response.json() == expected
        finally:
            await engine.dispose()


@pytest.mark.asyncio
async def test_harness_restarts_a_real_backend_process(tmp_path):
    async with CoachAppProcess(
        database_path=tmp_path / "restart.db", media_root=tmp_path / "media"
    ) as app_process:
        original_pid = app_process.pid
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(f"{app_process.base_url}/api/health")
        assert response.status_code == 200
        await app_process.restart()
        assert app_process.pid != original_pid
        assert (tmp_path / "restart.db").exists()


@pytest.mark.asyncio
async def test_report_claim_recovers_only_after_real_process_restart(tmp_path):
    database_path = tmp_path / "report.db"
    async with CoachAppProcess(database_path, tmp_path / "media") as app_process:
        engine = create_sqlite_engine(f"sqlite+aiosqlite:///{database_path}")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            await seed_populated_report(factory)
            async with factory() as db:
                row = await db.get(InterviewSession, "populated-report")
                row.report_state = "building"
                row.report_build_reason = "initial_completion"
                row.report_job_id = "lost-process-report-job"
                row.report_started_at = datetime.utcnow() - timedelta(days=1)
                row.report_contract_version = "coach_conversational_report_v1"
                row.conversation_state = "reporting"
                db.add(
                    AsyncJob(
                        id=row.report_job_id,
                        type="coach_conversational_report",
                        status="pending",
                        updated_at=row.report_started_at,
                    )
                )
                await db.commit()
            async with factory() as db:
                assert (await db.get(InterviewSession, "populated-report")).report_state == "building"
            original_pid = app_process.pid
            await app_process.restart()
            assert app_process.pid != original_pid
            async with factory() as db:
                row = await db.get(InterviewSession, "populated-report")
                job = await db.get(AsyncJob, "lost-process-report-job")
                assert row.report_state == "failed"
                assert row.report_job_id is None
                assert row.conversation_state == "recoverable_error"
                assert job.status == "failed"
                event = await db.scalar(
                    select(InterviewSessionEvent).where(
                        InterviewSessionEvent.session_id == row.id,
                        InterviewSessionEvent.event_type == "report_rebuild_failed",
                    )
                )
                assert event.actor_type == "reconciler"
        finally:
            await engine.dispose()


@pytest.mark.asyncio
async def test_expired_deletion_claim_recovers_after_real_process_restart(tmp_path):
    database_path = tmp_path / "deletion.db"
    async with CoachAppProcess(database_path, tmp_path / "media") as app_process:
        engine = create_sqlite_engine(f"sqlite+aiosqlite:///{database_path}")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as db:
                db.add(synthetic_session(id="delete-session"))
                await db.commit()
                claim = await CoachPrivacyService(
                    ConversationalSessionRepository(db)
                ).claim_hard_deletion(
                    "delete-session", deletion_request(), now=datetime.utcnow()
                )
                await db.commit()
                row = await db.get(InterviewSession, claim.session_id)
                row.deletion_claim_expires_at = datetime.utcnow() - timedelta(minutes=1)
                await db.commit()
            original_pid = app_process.pid
            await app_process.restart()
            assert app_process.pid != original_pid
            async with factory() as db:
                row = await db.get(InterviewSession, claim.session_id)
                job = await db.get(AsyncJob, claim.job_id)
                assert row.deletion_state == "failed"
                assert row.deletion_error_code == "coach_deletion_claim_expired"
                assert job.status == "failed"
        finally:
            await engine.dispose()


@pytest.mark.asyncio
async def test_real_backend_deletion_removes_owned_media_and_keeps_receipt(tmp_path):
    database_path = tmp_path / "delete-route.db"
    media_root = tmp_path / "media"
    async with CoachAppProcess(database_path, media_root) as app_process:
        engine = create_sqlite_engine(f"sqlite+aiosqlite:///{database_path}")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        payload = b"synthetic owned audio, not personal data"
        owned_media = media_root / "delete-route-session" / "clip.webm"
        owned_media.parent.mkdir(parents=True)
        owned_media.write_bytes(payload)
        try:
            async with factory() as db:
                db.add(synthetic_session(id="delete-route-session"))
                await db.flush()
                db.add(
                    SessionQuestion(
                        id="delete-route-question",
                        session_id="delete-route-session",
                        question_num=1,
                        text="Synthetic question",
                        category="Behavioural",
                        order_in_session=1,
                    )
                )
                await db.flush()
                db.add(
                    SessionRecording(
                        id="delete-route-recording",
                        session_id="delete-route-session",
                        question_id="delete-route-question",
                        recording_type="audio",
                        attempt_state="completed",
                        audio_uri=str(owned_media),
                        audio_content_hash=hashlib.sha256(payload).hexdigest(),
                    )
                )
                await db.commit()
            command = deletion_request("delete-route-command").model_dump(mode="json")
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.post(
                    f"{app_process.base_url}/api/coach/sessions/delete-route-session/deletion-commands",
                    json=command,
                )
                assert response.status_code in {200, 202}, response.text
                async with asyncio.timeout(8):
                    while True:
                        async with factory() as db:
                            receipt = await db.scalar(select(CoachSessionDeletionResult))
                            if receipt is not None and receipt.result_state != "processing":
                                assert receipt.result_state == "completed"
                                assert await db.get(InterviewSession, "delete-route-session") is None
                                break
                        await asyncio.sleep(0.05)
                assert not owned_media.exists()
                replay = await client.post(
                    f"{app_process.base_url}/api/coach/sessions/delete-route-session/deletion-commands",
                    json=command,
                )
                assert replay.status_code == 200
                assert replay.json()["result_state"] == "completed"
        finally:
            await engine.dispose()
