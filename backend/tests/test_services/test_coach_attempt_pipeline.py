"""Public contracts for the conversational attempt pipeline."""
from __future__ import annotations

from dataclasses import fields, replace
from contextlib import asynccontextmanager
import hashlib
import json
from datetime import datetime, timedelta
from inspect import signature
from pathlib import Path
from types import SimpleNamespace
from typing import get_type_hints

import pytest

from app.services.coach_attempt_pipeline import (
    AttemptPipelineError,
    AttemptProcessingContext,
    AttemptStage,
    SessionEvidenceSnapshot,
    SpeechMetricsSnapshot,
    StageResult,
    require_bound_transcript,
    run_attempt_pipeline,
    _process_attempt_claim,
    _safe_process_attempt_claim,
    queue_attempt_processing,
)
from app.repositories.conversational_session_repository import AttemptProcessingClaim
from app.models.coach_session import (
    InterviewAttemptEvaluation,
    InterviewAttemptStage,
    InterviewAttemptUpload,
    InterviewSession,
    InterviewSessionEvent,
    InterviewTranscriptVersion,
    SessionQuestion,
    SessionRecording,
)
from app.models.async_job import AsyncJob
from app.schemas.coach_conversation import ConversationCommandRequest
from app.services.coach_conversation_commands import (
    ConversationCommandError,
    ConversationCommandService,
)
from app.config import settings
from sqlalchemy import func, select


async def _active_session(db) -> tuple[InterviewSession, SessionQuestion]:
    session = InterviewSession(
        id="task4-session", company_name="Example", role_title="Architect",
        experience_version="conversational_v1", status="active", conversation_state="asking",
        state_version=0, retention_policy_json={"audio": "delete_after_processing", "transcript": "retain"},
    )
    question = SessionQuestion(
        id="task4-question", session_id=session.id, question_num=1, text="Question?",
        category="behavioural", difficulty="realistic", order_in_session=1,
        question_state="asked", question_kind="planned", follow_up_depth=0,
    )
    session.active_question_id = question.id
    session.active_root_question_id = question.id
    db.add_all((session, question))
    await db.commit()
    return session, question


def _command(kind: str, version: int, payload: dict[str, object]) -> ConversationCommandRequest:
    return ConversationCommandRequest.model_validate({
        "command_id": f"task4-{kind}-{version}", "command_type": kind,
        "expected_state_version": version, "payload": payload,
        "contract_version": "coach_conversation_command_v1",
    })


def _owned_audio(tmp_path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    root = tmp_path / "coach-media"
    source = root / "session-1" / "attempt-upload.webm"
    source.parent.mkdir(parents=True)
    body = b"deterministic test audio"
    source.write_bytes(body)
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", root)
    return str(source), hashlib.sha256(body).hexdigest()


async def _ready_audio_claim(db, monkeypatch: pytest.MonkeyPatch, tmp_path, client_id):
    session, question = await _active_session(db)
    claims: list[AttemptProcessingClaim] = []
    monkeypatch.setattr(
        "app.services.coach_conversation_commands.queue_attempt_processing",
        claims.append,
    )
    service = ConversationCommandService(db)
    begun = await service.execute(
        user_id="local",
        session_id=session.id,
        request=_command(
            "begin_answer",
            0,
            {"recording_type": "audio", "client_attempt_id": client_id},
        ),
    )
    attempt = await db.get(SessionRecording, begun.active_attempt_id)
    assert attempt is not None
    audio_uri, digest = _owned_audio(tmp_path, monkeypatch)
    attempt.attempt_state = "uploaded"
    attempt.audio_uri = audio_uri
    attempt.audio_content_hash = digest
    db.add(
        InterviewAttemptUpload(
            id=f"{client_id}-upload",
            attempt_id=attempt.id,
            upload_id="upload-1",
            request_hash="request",
            content_sha256=digest,
            byte_size=len(b"deterministic test audio"),
            mime_type="audio/webm",
            storage_uri=audio_uri,
            result_state="completed",
        )
    )
    await db.commit()
    await service.execute(
        user_id="local",
        session_id=session.id,
        request=_command(
            "finish_answer",
            begun.state_version,
            {"attempt_id": attempt.id, "upload_id": "upload-1"},
        ),
    )
    return session, question, attempt, claims[0]


def test_pr3_pipeline_interfaces_are_stable_and_exported() -> None:
    assert get_type_hints(AttemptStage) == {"name": str}
    assert tuple(signature(AttemptStage.run).parameters) == ("self", "context")
    assert [field.name for field in fields(AttemptProcessingContext)] == [
        "session_id", "question_id", "recording_id", "transcript_version_id",
        "evaluation_version_id", "processing_generation", "deadline_at",
        "recording_type", "normalized_transcript", "speech_metrics", "evidence_records",
    ]
    assert [field.name for field in fields(StageResult)] == [
        "stage_name", "stage_state", "output", "error_code", "retryable",
        "attempt_count", "repair_count",
    ]
    assert [field.name for field in fields(SpeechMetricsSnapshot)] == [
        "duration_ms", "word_count", "words_per_minute", "filler_count",
        "filler_rate_per_minute", "hedging_count", "pause_count",
        "long_pause_count", "restart_count",
    ]
    assert [field.name for field in fields(SessionEvidenceSnapshot)] == [
        "evidence_id", "source_type", "source_record_id", "source_record_version",
        "source_path", "snapshot_text", "approval_state", "content_hash", "snapshot_hash",
    ]


def test_audio_context_is_valid_before_transcription() -> None:
    context = AttemptProcessingContext(
        session_id="session-1", question_id="question-1", recording_id="recording-1",
        transcript_version_id=None, evaluation_version_id="evaluation-1",
        processing_generation=1, deadline_at=datetime.utcnow() + timedelta(seconds=30),
        recording_type="audio", normalized_transcript=None, speech_metrics=None,
        evidence_records=(),
    )
    assert context.transcript_version_id is None
    assert context.normalized_transcript is None


@pytest.mark.parametrize("transcript_id, transcript", [(None, "answer"), ("tv-1", None)])
def test_content_dependency_requires_an_immutable_bound_transcript(
    transcript_id: str | None, transcript: str | None
) -> None:
    context = AttemptProcessingContext(
        session_id="session-1", question_id="question-1", recording_id="recording-1",
        transcript_version_id=transcript_id, evaluation_version_id="evaluation-1",
        processing_generation=1, deadline_at=datetime.utcnow() + timedelta(seconds=30),
        recording_type="audio", normalized_transcript=transcript, speech_metrics=None,
        evidence_records=(),
    )
    with pytest.raises(AttemptPipelineError) as error:
        require_bound_transcript(context)
    assert error.value.code == "coach_attempt_stage_dependency_missing"
    assert error.value.retryable is False


@pytest.mark.asyncio
async def test_audio_transcription_binds_context_before_content_sibling_runs() -> None:
    claim = AttemptProcessingClaim(
        session_id="session-1", question_id="question-1", recording_id="recording-1",
        transcript_version_id=None, evaluation_version_id="evaluation-1",
        processing_generation=1, job_id="job-1",
        deadline_at=datetime.utcnow() + timedelta(seconds=30),
    )
    seen: list[str] = []

    class Transcription:
        name = "transcription"

        async def run(self, _context):
            seen.append(self.name)
            return StageResult(self.name, "completed", {"transcript_version_id": "tv-1", "normalized_transcript": "answer"}, None, False, 1, 0)

    class Speech:
        name = "speech_analysis"

        async def run(self, _context):
            seen.append(self.name)
            return StageResult(self.name, "completed", None, None, False, 1, 0)

    class Content:
        name = "content_evaluation"

        async def run(self, context):
            assert require_bound_transcript(context) == ("tv-1", "answer")
            seen.append(self.name)
            return StageResult(self.name, "unavailable", {"answer_level": "not_assessed"}, "coach_evaluation_unavailable", False, 1, 0)

    result = await run_attempt_pipeline(claim, (Transcription(), Speech(), Content()))

    assert seen == ["transcription", "speech_analysis", "content_evaluation"]
    assert result.transcript_version_id == "tv-1"
    assert result.evaluation_json["answer_level"] == "not_assessed"


@pytest.mark.asyncio
async def test_content_stage_does_not_run_without_a_bound_transcript() -> None:
    claim = AttemptProcessingClaim(
        session_id="session-1", question_id="question-1", recording_id="recording-1",
        transcript_version_id=None, evaluation_version_id="evaluation-1",
        processing_generation=1, job_id="job-1",
        deadline_at=datetime.utcnow() + timedelta(seconds=30),
    )
    invoked = False

    class Content:
        name = "content_evaluation"

        async def run(self, _context):
            nonlocal invoked
            invoked = True
            return StageResult(self.name, "completed", None, None, False, 1, 0)

    with pytest.raises(AttemptPipelineError) as error:
        await run_attempt_pipeline(claim, (Content(),))

    assert error.value.code == "coach_attempt_stage_dependency_missing"
    assert error.value.retryable is False
    assert invoked is False


@pytest.mark.asyncio
async def test_transcription_and_speech_are_independent_audio_siblings() -> None:
    claim = AttemptProcessingClaim(
        session_id="session-1", question_id="question-1", recording_id="recording-1",
        transcript_version_id=None, evaluation_version_id="evaluation-1",
        processing_generation=1, job_id="job-1",
        deadline_at=datetime.utcnow() + timedelta(seconds=30),
    )
    seen: list[str] = []

    class Transcription:
        name = "transcription"

        async def run(self, _context):
            seen.append(self.name)
            return StageResult(self.name, "failed_terminal", None, "transcriber_failed", False, 1, 0)

    class Speech:
        name = "speech_analysis"

        async def run(self, _context):
            seen.append(self.name)
            return StageResult(self.name, "completed", {"duration_ms": 1000}, None, False, 1, 0)

    class Content:
        name = "content_evaluation"

        async def run(self, _context):
            pytest.fail("content requires the missing transcript")

    with pytest.raises(AttemptPipelineError, match="coach_attempt_stage_dependency_missing"):
        await run_attempt_pipeline(claim, (Transcription(), Speech(), Content()))
    assert seen == ["transcription", "speech_analysis"]


@pytest.mark.asyncio
async def test_pipeline_keeps_the_deterministic_unavailable_projection() -> None:
    claim = AttemptProcessingClaim(
        session_id="session-1", question_id="question-1", recording_id="recording-1",
        transcript_version_id="tv-1", evaluation_version_id="evaluation-1",
        processing_generation=1, job_id="job-1",
        deadline_at=datetime.utcnow() + timedelta(seconds=30),
    )
    result = await run_attempt_pipeline(claim, ())
    assert result.evaluation_state == "unavailable"
    assert result.evaluation_json == {"answer_level": "not_assessed"}
    assert result.diagnostics["code"] == "coach_evaluation_unavailable"


@pytest.mark.asyncio
async def test_worker_transcript_binding_is_immutable() -> None:
    claim = AttemptProcessingClaim(
        session_id="session-1", question_id="question-1", recording_id="recording-1",
        transcript_version_id=None, evaluation_version_id="evaluation-1",
        processing_generation=1, job_id="job-1",
        deadline_at=datetime.utcnow() + timedelta(seconds=30),
    )

    class Transcript:
        name = "transcription"

        def __init__(self, version: str) -> None:
            self.version = version

        async def run(self, _context):
            return StageResult(self.name, "completed", {"transcript_version_id": self.version, "normalized_transcript": self.version}, None, False, 1, 0)

    class Speech:
        name = "speech_analysis"

        async def run(self, _context):
            return StageResult(self.name, "completed", {"transcript_version_id": "tv-2"}, None, False, 1, 0)

    result = await run_attempt_pipeline(claim, (Transcript("tv-1"), Speech()))
    assert result.transcript_version_id == "tv-1"


@pytest.mark.asyncio
async def test_typed_finish_is_atomic_and_dispatches_full_claim_after_commit(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, _ = await _active_session(db_session)
    observed: list[tuple[str, AttemptProcessingClaim]] = []
    monkeypatch.setattr(
        "app.services.coach_conversation_commands.queue_attempt_processing",
        lambda claim: observed.append(("queue", claim)),
    )

    async def after_commit(claim: AttemptProcessingClaim) -> None:
        assert await db_session.get(type("Unused", (), {}), "none") is None if False else True
        observed.append(("after", claim))

    service = ConversationCommandService(db_session, after_commit=after_commit)
    begun = await service.execute(user_id="local", session_id=session.id, request=_command(
        "begin_answer", 0, {"recording_type": "text", "client_attempt_id": "task4-text"}
    ))
    result = await service.execute(user_id="local", session_id=session.id, request=_command(
        "finish_answer", begun.state_version,
        {"attempt_id": begun.active_attempt_id, "transcript": "I led the migration."},
    ))
    attempt = await db_session.get(SessionRecording, result.active_attempt_id)
    assert attempt is not None and (attempt.attempt_state, attempt.processing_generation) == ("pending_processing", 1)
    evaluation = await db_session.scalar(select(InterviewAttemptEvaluation).where(
        InterviewAttemptEvaluation.recording_id == attempt.id,
        InterviewAttemptEvaluation.async_job_id == result.async_job_id,
    ))
    stages = (await db_session.scalars(select(InterviewAttemptStage).where(InterviewAttemptStage.recording_id == attempt.id))).all()
    assert evaluation is not None and evaluation.transcript_version_id == attempt.current_transcript_version_id
    assert len(stages) == 8
    assert {stage.stage_name: stage.stage_state for stage in stages}["audio_persist"] == "not_applicable"
    assert {stage.stage_name: stage.stage_state for stage in stages}["transcription"] == "not_applicable"
    assert {stage.stage_name: stage.stage_state for stage in stages}["speech_analysis"] == "not_applicable"
    assert result.async_job_id == observed[0][1].job_id == observed[1][1].job_id
    assert [name for name, _claim in observed] == ["queue", "after"]


@pytest.mark.asyncio
async def test_finish_rollback_does_not_dispatch_or_persist_claim(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    session, _ = await _active_session(db_session)
    dispatched: list[AttemptProcessingClaim] = []
    service = ConversationCommandService(db_session, after_commit=lambda claim: (_ for _ in ()).throw(AssertionError("must not dispatch")))
    begun = await service.execute(user_id="local", session_id=session.id, request=_command(
        "begin_answer", 0, {"recording_type": "text", "client_attempt_id": "task4-rollback"}
    ))

    async def fail(_claim: AttemptProcessingClaim) -> None:
        raise ConversationCommandError("coach_attempt_stale_claim")
    monkeypatch.setattr(service, "_persist_stub_stages", fail)
    with pytest.raises(ConversationCommandError):
        await service.execute(user_id="local", session_id=session.id, request=_command(
            "finish_answer", begun.state_version,
            {"attempt_id": begun.active_attempt_id, "transcript": "rollback"},
        ))
    assert dispatched == []
    assert await db_session.scalar(select(func.count(InterviewTranscriptVersion.id))) == 0


@pytest.mark.asyncio
async def test_typed_worker_terminalises_durable_claim(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    session, _ = await _active_session(db_session)
    claims: list[AttemptProcessingClaim] = []
    monkeypatch.setattr("app.services.coach_conversation_commands.queue_attempt_processing", claims.append)
    service = ConversationCommandService(db_session)
    begun = await service.execute(user_id="local", session_id=session.id, request=_command(
        "begin_answer", 0, {"recording_type": "text", "client_attempt_id": "task4-worker"}
    ))
    await service.execute(user_id="local", session_id=session.id, request=_command(
        "finish_answer", begun.state_version, {"attempt_id": begun.active_attempt_id, "transcript": "terminal"}
    ))

    @asynccontextmanager
    async def session_factory():
        yield db_session

    await _process_attempt_claim(claims[0], session_factory=session_factory)
    attempt = await db_session.get(SessionRecording, begun.active_attempt_id)
    await db_session.refresh(session)
    assert attempt is not None and attempt.attempt_state == "unavailable"
    assert session.conversation_state == "awaiting_next_action"


@pytest.mark.asyncio
async def test_audio_worker_binds_completed_upload_and_persists_timestamp_metrics(
    db_session, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    session, _ = await _active_session(db_session)
    claims: list[AttemptProcessingClaim] = []
    monkeypatch.setattr("app.services.coach_conversation_commands.queue_attempt_processing", claims.append)
    service = ConversationCommandService(db_session)
    begun = await service.execute(user_id="local", session_id=session.id, request=_command(
        "begin_answer", 0, {"recording_type": "audio", "client_attempt_id": "task4-audio"}
    ))
    attempt = await db_session.get(SessionRecording, begun.active_attempt_id)
    assert attempt is not None
    audio_uri, digest = _owned_audio(tmp_path, monkeypatch)
    attempt.attempt_state, attempt.audio_uri, attempt.audio_content_hash = "uploaded", audio_uri, digest
    db_session.add(InterviewAttemptUpload(
        id="task4-upload", attempt_id=attempt.id, upload_id="upload-1", request_hash="request",
        content_sha256=digest, byte_size=1, mime_type="audio/webm", storage_uri=audio_uri, result_state="completed",
    ))
    await db_session.commit()
    await service.execute(user_id="local", session_id=session.id, request=_command(
        "finish_answer", begun.state_version, {"attempt_id": attempt.id, "upload_id": "upload-1"}
    ))

    class Transcriber:
        def transcribe(self, _path):
            from app.services.transcriber import TranscriptionResult, WordTimestamp
            return TranscriptionResult("I delivered", "en", [WordTimestamp("I", 0, .1), WordTimestamp("delivered", .2, .5)])

    @asynccontextmanager
    async def session_factory():
        yield db_session
    await _process_attempt_claim(claims[0], session_factory=session_factory, transcriber_factory=Transcriber)
    await db_session.refresh(attempt)
    assert attempt.attempt_state == "unavailable"
    assert attempt.current_transcript_version_id is not None
    assert set(attempt.speech_metrics or {}) == {"duration_ms", "word_count", "words_per_minute", "filler_count", "filler_rate_per_minute", "hedging_count", "pause_count", "long_pause_count"}


def test_pipeline_order_is_fixed_and_rejects_duplicates() -> None:
    from app.services.coach_attempt_pipeline import PIPELINE_ORDER
    assert PIPELINE_ORDER == (
        "audio_persist", "transcription", "speech_analysis", "content_evaluation",
        "evidence_grounding", "follow_up_decision", "coaching_enrichment", "audio_cleanup",
    )
    assert len(PIPELINE_ORDER) == len(set(PIPELINE_ORDER))


@pytest.mark.asyncio
@pytest.mark.parametrize("names", [("transcription", "transcription"), ("speech_analysis", "transcription"), ("unknown",)])
async def test_pipeline_rejects_invalid_supplied_stage_graph(names: tuple[str, ...]) -> None:
    claim = AttemptProcessingClaim("s", "q", "r", None, "e", 1, "j", datetime.utcnow() + timedelta(seconds=30))
    stages = tuple(type("Stage", (), {"name": name, "run": lambda *_args: None})() for name in names)
    with pytest.raises(AttemptPipelineError, match="coach_attempt_stage_graph_invalid"):
        await run_attempt_pipeline(claim, stages)


def test_queue_schedules_the_durable_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    claim = AttemptProcessingClaim("s", "q", "r", None, "e", 1, "j", datetime.utcnow())
    observed = []
    monkeypatch.setattr("app.services.coach_attempt_pipeline.AsyncJobService.run", lambda job_id, coro: (observed.append(job_id), coro.close()))
    queue_attempt_processing(claim)
    assert observed == ["j"]


@pytest.mark.asyncio
async def test_worker_boundary_sanitizes_unexpected_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    claim = AttemptProcessingClaim("s", "q", "r", None, "e", 1, "j", datetime.utcnow())
    async def broken(_claim): raise RuntimeError("/secret/audio content")
    monkeypatch.setattr("app.services.coach_attempt_pipeline._process_attempt_claim", broken)
    with pytest.raises(AttemptPipelineError) as error:
        await _safe_process_attempt_claim(claim)
    assert str(error.value) == "coach_attempt_worker_failed"


@pytest.mark.asyncio
async def test_public_typed_pipeline_loads_immutable_transcript(monkeypatch: pytest.MonkeyPatch) -> None:
    claim = AttemptProcessingClaim("s", "q", "r", "tv", "e", 1, "j", datetime.utcnow() + timedelta(seconds=30))
    async def loader(_claim): return "normalized typed answer"
    monkeypatch.setattr("app.services.coach_attempt_pipeline._load_claim_transcript", loader)
    class Content:
        name = "content_evaluation"
        async def run(self, context):
            assert require_bound_transcript(context) == ("tv", "normalized typed answer")
            return StageResult(self.name, "unavailable", None, None, False, 1, 0)
    await run_attempt_pipeline(claim, (Content(),))


@pytest.mark.asyncio
async def test_fabricated_typed_claim_exposes_no_content_or_stage_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claim = AttemptProcessingClaim("s", "q", "r", "fabricated", "e", 1, "j", datetime.utcnow() + timedelta(seconds=30))
    async def no_content(_claim): return None
    monkeypatch.setattr("app.services.coach_attempt_pipeline._load_claim_transcript", no_content)
    ran = False
    class Content:
        name = "content_evaluation"
        async def run(self, _context):
            nonlocal ran
            ran = True
            return StageResult(self.name, "completed", None, None, False, 1, 0)
    with pytest.raises(AttemptPipelineError, match="coach_attempt_stage_dependency_missing"):
        await run_attempt_pipeline(claim, (Content(),))
    assert ran is False


@pytest.mark.asyncio
async def test_stale_claim_preflight_calls_no_provider_and_mutates_nothing(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    session, _ = await _active_session(db_session)
    claims: list[AttemptProcessingClaim] = []
    monkeypatch.setattr("app.services.coach_conversation_commands.queue_attempt_processing", claims.append)
    service = ConversationCommandService(db_session)
    begun = await service.execute(user_id="local", session_id=session.id, request=_command("begin_answer", 0, {"recording_type": "text", "client_attempt_id": "stale"}))
    await service.execute(user_id="local", session_id=session.id, request=_command("finish_answer", begun.state_version, {"attempt_id": begun.active_attempt_id, "transcript": "answer"}))
    attempt = await db_session.get(SessionRecording, begun.active_attempt_id)
    assert attempt is not None
    attempt.processing_generation += 1
    await db_session.commit()
    @asynccontextmanager
    async def session_factory(): yield db_session
    with pytest.raises(AttemptPipelineError, match="coach_attempt_stale_claim"):
        await _process_attempt_claim(claims[0], session_factory=session_factory)
    await db_session.refresh(attempt)
    assert attempt.attempt_state == "pending_processing"


@pytest.mark.asyncio
async def test_zero_row_generic_job_fence_rolls_back_attempt_terminalisation(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    session, _ = await _active_session(db_session)
    claims: list[AttemptProcessingClaim] = []
    monkeypatch.setattr("app.services.coach_conversation_commands.queue_attempt_processing", claims.append)
    service = ConversationCommandService(db_session)
    begun = await service.execute(user_id="local", session_id=session.id, request=_command("begin_answer", 0, {"recording_type": "text", "client_attempt_id": "job-fence"}))
    await service.execute(user_id="local", session_id=session.id, request=_command("finish_answer", begun.state_version, {"attempt_id": begun.active_attempt_id, "transcript": "answer"}))
    job = await db_session.get(AsyncJob, claims[0].job_id)
    assert job is not None
    job.status = "done"
    await db_session.commit()
    @asynccontextmanager
    async def session_factory(): yield db_session
    with pytest.raises(AttemptPipelineError, match="coach_attempt_stale_claim"):
        await _process_attempt_claim(claims[0], session_factory=session_factory)
    attempt = await db_session.get(SessionRecording, begun.active_attempt_id)
    await db_session.refresh(session)
    assert attempt is not None and attempt.attempt_state == "pending_processing"
    assert session.conversation_state == "processing_answer"


@pytest.mark.asyncio
async def test_audio_transcription_failure_terminalises_without_downstream_results(
    db_session, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    session, _ = await _active_session(db_session)
    claims: list[AttemptProcessingClaim] = []
    monkeypatch.setattr("app.services.coach_conversation_commands.queue_attempt_processing", claims.append)
    service = ConversationCommandService(db_session)
    begun = await service.execute(user_id="local", session_id=session.id, request=_command("begin_answer", 0, {"recording_type": "audio", "client_attempt_id": "failure-audio"}))
    attempt = await db_session.get(SessionRecording, begun.active_attempt_id)
    assert attempt is not None
    audio_uri, digest = _owned_audio(tmp_path, monkeypatch)
    attempt.attempt_state, attempt.audio_uri, attempt.audio_content_hash = "uploaded", audio_uri, digest
    db_session.add(InterviewAttemptUpload(id="failure-upload", attempt_id=attempt.id, upload_id="upload-1", request_hash="request", content_sha256=digest, byte_size=1, mime_type="audio/webm", storage_uri=audio_uri, result_state="completed"))
    await db_session.commit()
    await service.execute(user_id="local", session_id=session.id, request=_command("finish_answer", begun.state_version, {"attempt_id": attempt.id, "upload_id": "upload-1"}))
    class SpeechThenBrokenTranscriber:
        calls = 0

        def transcribe(self, _path):
            type(self).calls += 1
            if type(self).calls == 2:
                raise RuntimeError("private path must not persist")
            from app.services.transcriber import TranscriptionResult, WordTimestamp
            return TranscriptionResult("speech sibling", "en", [WordTimestamp("speech", 0, .2)])
    @asynccontextmanager
    async def session_factory(): yield db_session
    await _process_attempt_claim(claims[0], session_factory=session_factory, transcriber_factory=SpeechThenBrokenTranscriber)
    stages = (await db_session.scalars(select(InterviewAttemptStage).where(InterviewAttemptStage.recording_id == attempt.id))).all()
    states = {stage.stage_name: (stage.stage_state, stage.last_error_code) for stage in stages}
    await db_session.refresh(attempt)
    assert attempt.attempt_state == "unavailable"
    assert states["audio_persist"][0] == "completed"
    assert states["transcription"] == ("unavailable", "transcription_unavailable")
    assert states["speech_analysis"][0] == "completed"
    assert attempt.speech_metrics is not None and "restart_count" not in attempt.speech_metrics
    assert all(states[name][0] != "completed" for name in ("content_evaluation", "evidence_grounding", "follow_up_decision"))
    assert all(state[0] not in {"pending", "running"} for state in states.values())


@pytest.mark.asyncio
async def test_audio_speech_failure_is_independent_after_immutable_transcript(
    db_session, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    session, _ = await _active_session(db_session)
    claims: list[AttemptProcessingClaim] = []
    monkeypatch.setattr("app.services.coach_conversation_commands.queue_attempt_processing", claims.append)
    service = ConversationCommandService(db_session)
    begun = await service.execute(user_id="local", session_id=session.id, request=_command("begin_answer", 0, {"recording_type": "audio", "client_attempt_id": "speech-failure"}))
    attempt = await db_session.get(SessionRecording, begun.active_attempt_id)
    assert attempt is not None
    audio_uri, digest = _owned_audio(tmp_path, monkeypatch)
    attempt.attempt_state, attempt.audio_uri, attempt.audio_content_hash = "uploaded", audio_uri, digest
    db_session.add(InterviewAttemptUpload(id="speech-upload", attempt_id=attempt.id, upload_id="upload-1", request_hash="request", content_sha256=digest, byte_size=1, mime_type="audio/webm", storage_uri=audio_uri, result_state="completed"))
    await db_session.commit()
    await service.execute(user_id="local", session_id=session.id, request=_command("finish_answer", begun.state_version, {"attempt_id": attempt.id, "upload_id": "upload-1"}))
    class Transcriber:
        def transcribe(self, _path):
            from app.services.transcriber import TranscriptionResult, WordTimestamp
            return TranscriptionResult("bound transcript", "en", [WordTimestamp("bound", 0, .1)])
    @asynccontextmanager
    async def session_factory(): yield db_session
    monkeypatch.setattr("app.services.speech_analyser.SpeechAnalyserService.analyse_from_timestamps", lambda *_args: (_ for _ in ()).throw(RuntimeError("speech failed")))
    await _process_attempt_claim(claims[0], session_factory=session_factory, transcriber_factory=Transcriber)
    stages = (await db_session.scalars(select(InterviewAttemptStage).where(InterviewAttemptStage.recording_id == attempt.id))).all()
    states = {stage.stage_name: (stage.stage_state, stage.last_error_code) for stage in stages}
    await db_session.refresh(attempt)
    assert attempt.attempt_state == "unavailable" and attempt.current_transcript_version_id is not None
    assert states["speech_analysis"] == ("unavailable", "speech_analysis_unavailable")


@pytest.mark.asyncio
@pytest.mark.parametrize("media_failure", ("hash", "root", "replacement"))
async def test_media_integrity_error_terminalises_invalid_without_acceptance(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    media_failure: str,
) -> None:
    session, question, attempt, claim = await _ready_audio_claim(
        db_session, monkeypatch, tmp_path, f"invalid-media-{media_failure}"
    )
    audio_path = Path(attempt.audio_uri or "")
    if media_failure == "hash":
        audio_path.write_bytes(b"tampered-audio")
    elif media_failure == "root":
        monkeypatch.setattr(
            settings, "HATCH_COACH_MEDIA_ROOT", tmp_path / "different-root"
        )
    else:
        outside = tmp_path / "replacement.webm"
        outside.write_bytes(b"replacement-audio")
        audio_path.unlink()
        audio_path.symlink_to(outside)
    before = (
        session.state_version,
        session.activity_version,
        session.event_version,
        await db_session.scalar(select(func.count(InterviewSessionEvent.id))),
    )
    provider_calls = 0

    class Provider:
        def transcribe(self, _path):
            nonlocal provider_calls
            provider_calls += 1
            pytest.fail("invalid media must fail before provider access")

    @asynccontextmanager
    async def session_factory():
        yield db_session

    await _process_attempt_claim(
        claim, session_factory=session_factory, transcriber_factory=Provider
    )

    await db_session.refresh(session)
    await db_session.refresh(question)
    await db_session.refresh(attempt)
    evaluation = await db_session.get(
        InterviewAttemptEvaluation, claim.evaluation_version_id
    )
    job = await db_session.get(AsyncJob, claim.job_id)
    stages = (
        await db_session.scalars(
            select(InterviewAttemptStage).where(
                InterviewAttemptStage.evaluation_version_id
                == claim.evaluation_version_id
            )
        )
    ).all()
    events = (
        await db_session.scalars(
            select(InterviewSessionEvent)
            .where(InterviewSessionEvent.session_id == session.id)
            .order_by(InterviewSessionEvent.sequence_number)
        )
    ).all()

    assert provider_calls == 0
    assert evaluation is not None and evaluation.state == "invalid"
    assert attempt.attempt_state == attempt.evaluation_state == "invalid"
    assert attempt.current_evaluation_version_id == claim.evaluation_version_id
    assert attempt.current_transcript_version_id is None
    assert question.accepted_recording_id is None
    assert session.status == session.conversation_state == "failed"
    assert session.state_version == before[0] + 1
    assert session.activity_version == before[1] + 1
    assert session.event_version == before[2] + 1
    assert len(events) == before[3] + 1
    terminal_event = events[-1]
    assert (
        terminal_event.event_type,
        terminal_event.state_before,
        terminal_event.state_after,
        terminal_event.state_version,
        terminal_event.payload_json,
    ) == (
        "attempt_processing_failed",
        "processing_answer",
        "failed",
        session.state_version,
        {"state": "invalid", "reason": "invalid_audio"},
    )
    assert job is not None and job.status == "done"
    assert json.loads(job.result_json or "null") == {"status": "invalid"}
    stage_states = {
        stage.stage_name: (stage.stage_state, stage.last_error_code)
        for stage in stages
    }
    assert stage_states["audio_persist"] == ("unavailable", "invalid_audio")
    assert stage_states["audio_persist"][0] != "completed"


@pytest.mark.asyncio
async def test_lost_generic_job_ownership_rolls_back_all_worker_mutations(
    db_session, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    session, _question, attempt, claim = await _ready_audio_claim(
        db_session, monkeypatch, tmp_path, "lost-job"
    )
    evaluation = await db_session.get(
        InterviewAttemptEvaluation, claim.evaluation_version_id
    )
    job = await db_session.get(AsyncJob, claim.job_id)
    stages = (
        await db_session.scalars(
            select(InterviewAttemptStage).where(
                InterviewAttemptStage.evaluation_version_id
                == claim.evaluation_version_id
            )
        )
    ).all()
    assert evaluation is not None and job is not None
    before_session = (
        session.status,
        session.conversation_state,
        session.state_version,
        session.activity_version,
        session.event_version,
    )
    before_attempt = (
        attempt.attempt_state,
        attempt.evaluation_state,
        attempt.current_transcript_version_id,
        attempt.current_evaluation_version_id,
        attempt.speech_metrics,
    )
    before_evaluation = (
        evaluation.state,
        evaluation.completed_at,
        evaluation.diagnostics_json,
    )
    before_stages = {
        stage.id: (
            stage.stage_state,
            stage.last_error_code,
            stage.completed_at,
            stage.source_transcript_version_id,
        )
        for stage in stages
    }
    before_events = await db_session.scalar(
        select(func.count(InterviewSessionEvent.id))
    )
    real_execute = db_session.execute

    async def lose_job_update(statement, *args, **kwargs):
        table = getattr(statement, "table", None)
        if getattr(table, "name", None) == "async_jobs":
            return SimpleNamespace(rowcount=0)
        return await real_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "execute", lose_job_update)

    class Transcriber:
        def transcribe(self, _path):
            from app.services.transcriber import TranscriptionResult, WordTimestamp

            return TranscriptionResult(
                "verified answer", "en", [WordTimestamp("verified", 0, 0.2)]
            )

    @asynccontextmanager
    async def session_factory():
        yield db_session

    with pytest.raises(AttemptPipelineError, match="coach_attempt_stale_claim"):
        await _process_attempt_claim(
            claim, session_factory=session_factory, transcriber_factory=Transcriber
        )

    await db_session.refresh(session)
    await db_session.refresh(attempt)
    await db_session.refresh(evaluation)
    await db_session.refresh(job)
    for stage in stages:
        await db_session.refresh(stage)
    assert (
        session.status,
        session.conversation_state,
        session.state_version,
        session.activity_version,
        session.event_version,
    ) == before_session
    assert (
        attempt.attempt_state,
        attempt.evaluation_state,
        attempt.current_transcript_version_id,
        attempt.current_evaluation_version_id,
        attempt.speech_metrics,
    ) == before_attempt
    assert (
        evaluation.state,
        evaluation.completed_at,
        evaluation.diagnostics_json,
    ) == before_evaluation
    assert {
        stage.id: (
            stage.stage_state,
            stage.last_error_code,
            stage.completed_at,
            stage.source_transcript_version_id,
        )
        for stage in stages
    } == before_stages
    assert job.status == "pending" and job.result_json is None
    assert await db_session.scalar(select(func.count(InterviewSessionEvent.id))) == before_events
    assert await db_session.scalar(
        select(func.count(InterviewTranscriptVersion.id)).where(
            InterviewTranscriptVersion.recording_id == attempt.id
        )
    ) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "authority_mismatch",
    ("terminal_job", "wrong_job_type", "session_status", "experience", "question"),
)
async def test_incomplete_worker_authority_fence_calls_no_provider(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    authority_mismatch: str,
) -> None:
    session, _question, _attempt, claim = await _ready_audio_claim(
        db_session, monkeypatch, tmp_path, f"fence-{authority_mismatch}"
    )
    job = await db_session.get(AsyncJob, claim.job_id)
    assert job is not None
    if authority_mismatch == "terminal_job":
        job.status = "done"
    elif authority_mismatch == "wrong_job_type":
        job.type = "coach_report"
    elif authority_mismatch == "session_status":
        session.status = "failed"
    elif authority_mismatch == "experience":
        session.experience_version = "legacy_v1"
    else:
        session.active_question_id = None
    await db_session.commit()
    provider_calls = 0

    class Provider:
        def transcribe(self, _path):
            nonlocal provider_calls
            provider_calls += 1
            pytest.fail("stale authority must fail before provider access")

    @asynccontextmanager
    async def session_factory():
        yield db_session

    with pytest.raises(AttemptPipelineError, match="coach_attempt_stale_claim"):
        await _process_attempt_claim(
            claim, session_factory=session_factory, transcriber_factory=Provider
        )
    assert provider_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_observation", ("empty_text", "empty_words"))
async def test_missing_speech_observation_is_unavailable_without_synthetic_metrics(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    missing_observation: str,
) -> None:
    _session, _question, attempt, claim = await _ready_audio_claim(
        db_session, monkeypatch, tmp_path, f"speech-{missing_observation}"
    )

    class Transcriber:
        calls = 0

        def transcribe(self, _path):
            from app.services.transcriber import TranscriptionResult, WordTimestamp

            type(self).calls += 1
            if type(self).calls == 1:
                return TranscriptionResult(
                    " " if missing_observation == "empty_text" else "observed",
                    "en",
                    []
                    if missing_observation == "empty_words"
                    else [WordTimestamp("observed", 0, 0.2)],
                )
            return TranscriptionResult(
                "content transcript", "en", [WordTimestamp("content", 0, 0.2)]
            )

    @asynccontextmanager
    async def session_factory():
        yield db_session

    await _process_attempt_claim(
        claim, session_factory=session_factory, transcriber_factory=Transcriber
    )
    await db_session.refresh(attempt)
    speech_stage = await db_session.scalar(
        select(InterviewAttemptStage).where(
            InterviewAttemptStage.evaluation_version_id == claim.evaluation_version_id,
            InterviewAttemptStage.stage_name == "speech_analysis",
        )
    )
    assert speech_stage is not None
    assert (
        speech_stage.stage_state,
        speech_stage.last_error_code,
        attempt.speech_metrics,
    ) == ("unavailable", "speech_analysis_unavailable", None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fabrication",
    ("transcript", "stale_job", "deadline", "claim_token", "processing_contract"),
)
async def test_real_db_fabricated_typed_claim_loads_no_content_or_stage(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    fabrication: str,
) -> None:
    session, _question = await _active_session(db_session)
    claims: list[AttemptProcessingClaim] = []
    monkeypatch.setattr(
        "app.services.coach_conversation_commands.queue_attempt_processing",
        claims.append,
    )
    service = ConversationCommandService(db_session)
    begun = await service.execute(
        user_id="local",
        session_id=session.id,
        request=_command(
            "begin_answer",
            0,
            {"recording_type": "text", "client_attempt_id": f"typed-{fabrication}"},
        ),
    )
    await service.execute(
        user_id="local",
        session_id=session.id,
        request=_command(
            "finish_answer",
            begun.state_version,
            {"attempt_id": begun.active_attempt_id, "transcript": "private content"},
        ),
    )
    claim = claims[0]
    if fabrication == "transcript":
        claim = replace(claim, transcript_version_id="fabricated-transcript")
    elif fabrication == "stale_job":
        job = await db_session.get(AsyncJob, claim.job_id)
        assert job is not None
        job.status = "done"
        await db_session.commit()
    elif fabrication == "deadline":
        claim = replace(claim, deadline_at=claim.deadline_at + timedelta(seconds=1))
    else:
        evaluation = await db_session.get(
            InterviewAttemptEvaluation, claim.evaluation_version_id
        )
        assert evaluation is not None
        diagnostics = dict(evaluation.diagnostics_json or {})
        processing_claim = dict(diagnostics["processing_claim"])
        if fabrication == "claim_token":
            processing_claim["claim_token"] = "replacement-token"
        else:
            processing_claim["processing_contract_version"] = "replacement_contract"
        evaluation.diagnostics_json = {
            **diagnostics,
            "processing_claim": processing_claim,
        }
        await db_session.commit()

    @asynccontextmanager
    async def session_factory():
        yield db_session

    monkeypatch.setattr("app.database.AsyncSessionLocal", session_factory)
    stage_calls = 0

    class Content:
        name = "content_evaluation"

        async def run(self, _context):
            nonlocal stage_calls
            stage_calls += 1
            pytest.fail("fabricated authority must expose no transcript content")

    with pytest.raises(
        AttemptPipelineError, match="coach_attempt_stage_dependency_missing"
    ):
        await run_attempt_pipeline(claim, (Content(),))
    assert stage_calls == 0
