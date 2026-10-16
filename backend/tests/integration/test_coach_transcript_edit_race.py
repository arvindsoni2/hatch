"""V6 Scenario E: an audio transcript edit fences a late old worker."""

import asyncio
import base64
import hashlib
from datetime import datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import create_sqlite_engine
from app.models.coach_session import (
    InterviewAttemptEvaluation,
    InterviewAttemptStage,
    InterviewTranscriptVersion,
    SessionRecording,
)
from app.repositories.conversational_session_repository import (
    AttemptProcessingClaim,
    AttemptProcessingResult,
    ConversationalSessionRepository,
)
from app.services.coach_processing_snapshot import _claim_source_transcript_is_valid
from coach_app_process import CoachAppProcess
from test_coach_degraded_ai_journey import AUDIO_FIXTURE, _command, _wait_for_setup


ORIGINAL = (
    "In the synthetic migration I coordinated the release across two teams. "
    "I mapped dependencies, assigned owners, and wrote a reversible deployment "
    "checklist. When a test failed, I paused the rollout, isolated the failing "
    "service, and reran checks. The team then shipped safely and reduced "
    "deployment time by three hours."
)
EDITED = "I coordinated the migration and resolved the release issue."


async def _wait_for_review(client, base_url, session_id):
    async with asyncio.timeout(30):
        while True:
            response = await client.get(f"{base_url}/api/coach/sessions/{session_id}/live")
            if response.status_code == 409:
                await asyncio.sleep(0.1)
                continue
            assert response.status_code == 200, response.text
            live = response.json()
            if live["conversation_state"] == "awaiting_next_action":
                return live
            await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_audio_edit_fences_late_old_finalizer_and_preserves_delivery(tmp_path):
    """A stale generation cannot replace the corrected review or audio delivery."""
    database_path = tmp_path / "edit-race.db"
    async with CoachAppProcess(
        database_path,
        tmp_path / "media",
        app_module="coach_edit_race_test_server:app",
    ) as app_process:
        base_url = app_process.base_url
        async with httpx.AsyncClient(timeout=5) as client:
            created = await client.post(
                f"{base_url}/api/coach/sessions",
                json={
                    "company_name": "Synthetic Edit Co",
                    "role_title": "Engineer",
                    "jd_text": "Build reliable software.",
                    "experience_version": "conversational_v1",
                    "conversational_config": {
                        "interview_type": "mixed",
                        "difficulty": "realistic",
                        "duration_minutes": 30,
                        "planned_question_count": 6,
                        "role_family": "software_engineering",
                        "role_level": "senior",
                        "industry": "technology",
                        "locale": "en-GB",
                        "focus_areas": ["delivery_execution"],
                        "allowed_answer_modes": ["text", "audio"],
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
            assert created.status_code == 202, created.text
            session_id = created.json()["session_id"]
            await _wait_for_setup(client, base_url, created.json()["job_id"])
            await _command(client, base_url, session_id, "start", {})
            begun = await _command(
                client,
                base_url,
                session_id,
                "begin_answer",
                {"recording_type": "audio", "client_attempt_id": str(uuid4())},
            )
            attempt_id = begun["active_attempt_id"]
            audio = base64.b64decode(AUDIO_FIXTURE.read_text(encoding="ascii"))
            upload_id = str(uuid4())
            uploaded = await client.post(
                f"{base_url}/api/coach/sessions/{session_id}/attempts/{attempt_id}/audio",
                data={"upload_id": upload_id, "content_sha256": hashlib.sha256(audio).hexdigest()},
                files={"audio": ("synthetic-tone.webm", audio, "audio/webm")},
            )
            assert uploaded.status_code == 200, uploaded.text
            await _command(
                client,
                base_url,
                session_id,
                "finish_answer",
                {"attempt_id": attempt_id, "upload_id": upload_id},
            )
            original_live = await _wait_for_review(client, base_url, session_id)
            assert original_live["active_attempt"]["transcript_version"]["transcript"] == ORIGINAL
            assert original_live["answer_review"]["evaluation_state"] == "completed"
            original_delivery = original_live["answer_review"]["delivery"]
            assert original_delivery["level"] != "not_assessed"

            engine = create_sqlite_engine(f"sqlite+aiosqlite:///{database_path}")
            factory = async_sessionmaker(engine, expire_on_commit=False)
            try:
                async with asyncio.timeout(10):
                    while True:
                        async with factory() as db:
                            attempt = await db.get(SessionRecording, attempt_id)
                            if attempt.audio_retention_state == "deleted":
                                break
                        await asyncio.sleep(0.1)
                async with factory() as db:
                    attempt = await db.get(SessionRecording, attempt_id)
                    assert attempt is not None
                    old_transcript_id = attempt.current_transcript_version_id
                    old_eval = await db.get(
                        InterviewAttemptEvaluation,
                        attempt.current_evaluation_version_id,
                    )
                    assert old_eval is not None and old_eval.async_job_id is not None
                    snapshot = old_eval.diagnostics_json["processing_claim"]
                    old_claim = AttemptProcessingClaim(
                        session_id=session_id,
                        question_id=attempt.question_id,
                        recording_id=attempt_id,
                        transcript_version_id=old_transcript_id,
                        evaluation_version_id=old_eval.id,
                        processing_generation=snapshot["processing_generation"],
                        job_id=old_eval.async_job_id,
                        deadline_at=datetime.fromisoformat(snapshot["job_deadline_at"]),
                    )
                    original_metrics = attempt.speech_metrics
                    original_rubric = dict(old_eval.rubric_json)
                    old_cleanup = await db.scalar(
                        select(InterviewAttemptStage).where(
                            InterviewAttemptStage.evaluation_version_id == old_eval.id,
                            InterviewAttemptStage.stage_name == "audio_cleanup",
                        )
                    )
                    assert old_cleanup is not None and old_cleanup.stage_state == "completed"
                    old_cleanup_job_id = old_cleanup.job_id

                edited = await _command(
                    client,
                    base_url,
                    session_id,
                    "edit_transcript",
                    {
                        "attempt_id": attempt_id,
                        "transcript": EDITED,
                        "edit_reason": "transcription_error",
                    },
                )
                assert edited["async_job_id"] != old_claim.job_id
                async with asyncio.timeout(20):
                    while not (tmp_path / "edit-evaluation-entered").exists():
                        await asyncio.sleep(0.05)

                try:
                    async with factory() as db:
                        attempt = await db.get(SessionRecording, attempt_id)
                        assert attempt is not None
                        assert attempt.processing_generation == old_claim.processing_generation + 1
                        assert attempt.attempt_state == "pending_processing"
                        assert attempt.current_transcript_version_id != old_transcript_id
                        new_eval = await db.scalar(
                            select(InterviewAttemptEvaluation).where(
                                InterviewAttemptEvaluation.recording_id == attempt_id,
                                InterviewAttemptEvaluation.state == "pending",
                            )
                        )
                        assert new_eval is not None
                        new_eval_id = new_eval.id
                        stale_applied = await ConversationalSessionRepository(
                            db
                        ).finalise_attempt_processing(
                            claim=old_claim,
                            result=AttemptProcessingResult(
                                evaluation_state="completed",
                                evaluation_json=original_rubric,
                                transcript_version_id=old_transcript_id,
                                diagnostics={},
                            ),
                        )
                        assert stale_applied is False
                        await db.commit()
                    async with factory() as db:
                        attempt = await db.get(SessionRecording, attempt_id)
                        assert attempt is not None
                        assert attempt.current_transcript_version_id != old_transcript_id
                        assert attempt.processing_generation == old_claim.processing_generation + 1
                        assert (await db.get(InterviewAttemptEvaluation, new_eval_id)).state == "pending"
                    async with factory() as db:
                        new_eval = await db.get(InterviewAttemptEvaluation, new_eval_id)
                        edited_transcript = await db.get(
                            InterviewTranscriptVersion, new_eval.transcript_version_id
                        )
                        claim_snapshot = new_eval.diagnostics_json["processing_claim"]
                        assert await _claim_source_transcript_is_valid(
                            db,
                            attempt=await db.get(SessionRecording, attempt_id),
                            evaluation=new_eval,
                            claim=claim_snapshot,
                        )
                        edited_transcript.created_by = "system"
                        await db.flush()
                        assert not await _claim_source_transcript_is_valid(
                            db,
                            attempt=await db.get(SessionRecording, attempt_id),
                            evaluation=new_eval,
                            claim=claim_snapshot,
                        )
                        await db.rollback()
                finally:
                    (tmp_path / "release-edit-evaluation").touch()

                edited_live = await _wait_for_review(client, base_url, session_id)
                assert edited_live["active_attempt"]["transcript_version"]["transcript"] == EDITED
                assert edited_live["answer_review"]["evaluation_id"] == new_eval_id
                assert edited_live["answer_review"]["evaluation_state"] == "completed"
                assert edited_live["answer_review"]["delivery"] == original_delivery

                async with factory() as db:
                    attempt = await db.get(SessionRecording, attempt_id)
                    old_eval = await db.get(InterviewAttemptEvaluation, old_claim.evaluation_version_id)
                    new_eval = await db.get(InterviewAttemptEvaluation, new_eval_id)
                    assert attempt is not None and old_eval is not None and new_eval is not None
                    assert attempt.speech_metrics == original_metrics
                    assert old_eval.state == "superseded"
                    assert new_eval.state == "completed"
                    assert new_eval.rubric_json["delivery"] == original_rubric["delivery"]
                    new_cleanup = await db.scalar(
                        select(InterviewAttemptStage).where(
                            InterviewAttemptStage.evaluation_version_id == new_eval_id,
                            InterviewAttemptStage.stage_name == "audio_cleanup",
                        )
                    )
                    assert new_cleanup is not None
                    assert new_cleanup.stage_state == "completed"
                    assert new_cleanup.job_id == old_cleanup_job_id
                    assert await db.scalar(
                        select(func.count(SessionRecording.id)).where(
                            SessionRecording.session_id == session_id
                        )
                    ) == 1
                    transcripts = (
                        await db.scalars(
                            select(InterviewTranscriptVersion)
                            .where(InterviewTranscriptVersion.recording_id == attempt_id)
                            .order_by(InterviewTranscriptVersion.version_number)
                        )
                    ).all()
                    assert [(row.transcript, row.source) for row in transcripts] == [
                        (ORIGINAL, "transcription"),
                        (EDITED, "candidate_edit"),
                    ]
            finally:
                await engine.dispose()
    log_text = (tmp_path / "coach-app-process.log").read_text(encoding="utf-8")
    assert "openai._base_client" not in log_text
    assert ORIGINAL not in log_text and EDITED not in log_text
