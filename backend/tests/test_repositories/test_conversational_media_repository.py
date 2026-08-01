"""Transactional tests for conversational attempt audio persistence."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.coach_session import (
    InterviewAttemptUpload,
    InterviewSession,
    SessionRecording,
)
from app.repositories.conversational_session_repository import (
    ConversationalRepositoryError,
    ConversationalSessionRepository,
)


@pytest_asyncio.fixture
async def repository_database(tmp_path: Path):
    database = tmp_path / "conversational-media.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


async def _seed_listening_attempt(
    factory: async_sessionmaker[AsyncSession],
    *,
    session_id: str = "session-1",
    attempt_id: str = "attempt-1",
    retention_policy: str = "delete_after_processing",
) -> None:
    async with factory.begin() as db:
        db.add(
            InterviewSession(
                id=session_id,
                company_name="Example",
                role_title="Engineer",
                experience_version="conversational_v1",
                status="active",
                conversation_state="listening",
                active_recording_id=attempt_id,
                retention_policy_json={"audio": retention_policy},
            )
        )
        db.add(
            SessionRecording(
                id=attempt_id,
                session_id=session_id,
                recording_type="audio",
                attempt_state="draft",
                audio_retention_policy=retention_policy,
                audio_retention_state="pending",
                processing_retry_limit=2,
                client_attempt_id="client-attempt-1",
            )
        )


def _stage(path: Path, body: bytes, mime_type: str = "audio/webm") -> SimpleNamespace:
    path.write_bytes(body)
    return SimpleNamespace(
        temporary_path=path,
        content_sha256=hashlib.sha256(body).hexdigest(),
        byte_size=len(body),
        mime_type=mime_type,
    )


@pytest.mark.asyncio
async def test_persist_audio_upload_updates_attempt_and_replays_without_a_second_row(
    repository_database, tmp_path: Path
) -> None:
    """Removing the completed-upload replay branch would duplicate the receipt."""
    await _seed_listening_attempt(repository_database)
    body = b"synthetic-webm"
    digest = hashlib.sha256(body).hexdigest()
    destination = tmp_path / "media" / "session-1" / "attempt-1-upload-1.webm"
    destination.parent.mkdir(parents=True)

    async with repository_database.begin() as db:
        first = await ConversationalSessionRepository(db).persist_audio_upload(
            session_id="session-1",
            attempt_id="attempt-1",
            upload_id="upload-1",
            declared_sha256=digest,
            staged=_stage(tmp_path / "first.tmp", body),
            destination=destination,
        )

    replay_path = tmp_path / "replay.tmp"
    async with repository_database.begin() as db:
        replay = await ConversationalSessionRepository(db).persist_audio_upload(
            session_id="session-1",
            attempt_id="attempt-1",
            upload_id="upload-1",
            declared_sha256=digest,
            staged=_stage(replay_path, body),
            destination=destination,
        )

    async with repository_database() as db:
        attempt = await db.get(SessionRecording, "attempt-1")
        upload_count = await db.scalar(select(func.count(InterviewAttemptUpload.id)))
    assert first == replay
    assert first.model_dump(mode="json") == {
        "attempt_id": "attempt-1",
        "upload_id": "upload-1",
        "result": "completed",
        "content_sha256": digest,
        "byte_size": len(body),
        "mime_type": "audio/webm",
        "audio_retention_state": "temporary",
        "contract_version": "coach_attempt_audio_upload_v1",
    }
    assert attempt is not None
    assert (attempt.attempt_state, attempt.audio_content_hash) == ("uploaded", digest)
    assert Path(attempt.audio_uri or "") == destination
    assert upload_count == 1
    assert destination.read_bytes() == body
    assert not replay_path.exists()


@pytest.mark.asyncio
async def test_persist_audio_upload_rejects_changed_hash_and_removes_staged_file(
    repository_database, tmp_path: Path
) -> None:
    """Accepting a reused upload ID with different bytes breaks idempotency."""
    await _seed_listening_attempt(repository_database)
    original = b"original-webm"
    destination = tmp_path / "media" / "session-1" / "attempt-1-upload-1.webm"
    destination.parent.mkdir(parents=True)
    async with repository_database.begin() as db:
        await ConversationalSessionRepository(db).persist_audio_upload(
            session_id="session-1",
            attempt_id="attempt-1",
            upload_id="upload-1",
            declared_sha256=hashlib.sha256(original).hexdigest(),
            staged=_stage(tmp_path / "first.tmp", original),
            destination=destination,
        )

    changed = b"changed-webm"
    changed_path = tmp_path / "changed.tmp"
    async with repository_database.begin() as db:
        with pytest.raises(
            ConversationalRepositoryError,
            match="coach_audio_upload_idempotency_conflict",
        ):
            await ConversationalSessionRepository(db).persist_audio_upload(
                session_id="session-1",
                attempt_id="attempt-1",
                upload_id="upload-1",
                declared_sha256=hashlib.sha256(changed).hexdigest(),
                staged=_stage(changed_path, changed),
                destination=destination,
            )

    async with repository_database() as db:
        upload_count = await db.scalar(select(func.count(InterviewAttemptUpload.id)))
    assert upload_count == 1
    assert destination.read_bytes() == original
    assert not changed_path.exists()


@pytest.mark.asyncio
async def test_persist_audio_upload_rejects_hash_mismatch_before_moving_bytes(
    repository_database, tmp_path: Path
) -> None:
    """Trusting the declared digest would persist tampered upload bytes."""
    await _seed_listening_attempt(repository_database)
    body = b"synthetic-webm"
    staged_path = tmp_path / "mismatch.tmp"
    destination = tmp_path / "media" / "session-1" / "attempt-1-upload-1.webm"
    destination.parent.mkdir(parents=True)

    async with repository_database.begin() as db:
        with pytest.raises(
            ConversationalRepositoryError,
            match="coach_attempt_upload_hash_mismatch",
        ):
            await ConversationalSessionRepository(db).persist_audio_upload(
                session_id="session-1",
                attempt_id="attempt-1",
                upload_id="upload-1",
                declared_sha256="0" * 64,
                staged=_stage(staged_path, body),
                destination=destination,
            )

    async with repository_database() as db:
        upload_count = await db.scalar(select(func.count(InterviewAttemptUpload.id)))
        attempt = await db.get(SessionRecording, "attempt-1")
    assert upload_count == 0
    assert attempt is not None and attempt.attempt_state == "draft"
    assert not staged_path.exists()
    assert not destination.exists()


@pytest.mark.asyncio
async def test_persist_audio_upload_rolls_back_and_removes_moved_file_on_flush_failure(
    repository_database, tmp_path: Path
) -> None:
    """Leaving the moved file after a failed flush creates unowned private data."""
    await _seed_listening_attempt(repository_database)
    body = b"synthetic-webm"
    digest = hashlib.sha256(body).hexdigest()
    staged_path = tmp_path / "failure.tmp"
    destination = tmp_path / "media" / "session-1" / "attempt-1-upload-1.webm"
    destination.parent.mkdir(parents=True)

    async with repository_database() as db:
        @event.listens_for(db.sync_session, "before_flush", once=True)
        def _fail_flush(_session, _flush_context, _instances) -> None:
            raise RuntimeError("injected database failure")

        with pytest.raises(
            ConversationalRepositoryError,
            match="coach_attempt_upload_conflict",
        ):
            await ConversationalSessionRepository(db).persist_audio_upload(
                session_id="session-1",
                attempt_id="attempt-1",
                upload_id="upload-1",
                declared_sha256=digest,
                staged=_stage(staged_path, body),
                destination=destination,
            )

        upload_count = await db.scalar(select(func.count(InterviewAttemptUpload.id)))
        attempt = await db.get(SessionRecording, "attempt-1")

    assert upload_count == 0
    assert attempt is not None
    assert (attempt.attempt_state, attempt.audio_uri, attempt.audio_content_hash) == (
        "draft",
        None,
        None,
    )
    assert not staged_path.exists()
    assert not destination.exists()
