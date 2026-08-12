"""Transactional tests for conversational attempt audio persistence."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from io import BytesIO
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
from app.services.coach_media_storage import (
    CoachMediaError,
    OwnedAudioPublication,
    cleanup_staged_audio,
    coach_upload_temp_dir,
    publish_staged_audio,
    resolve_owned_audio_path,
    stream_audio_upload,
)
from starlette.datastructures import Headers, UploadFile


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


def _request_hash(
    *, content_sha256: str, byte_size: int, mime_type: str = "audio/webm"
) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "attempt_id": "attempt-1",
                "byte_size": byte_size,
                "content_sha256": content_sha256,
                "mime_type": mime_type,
                "upload_id": "upload-1",
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


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

    async with repository_database() as db:
        repository = ConversationalSessionRepository(db)
        first = await repository.persist_audio_upload(
            session_id="session-1",
            attempt_id="attempt-1",
            upload_id="upload-1",
            declared_sha256=digest,
            staged=_stage(tmp_path / "first.tmp", body),
            destination=destination,
        )
        await repository.commit_audio_upload()

    replay_path = tmp_path / "replay.tmp"
    async with repository_database() as db:
        repository = ConversationalSessionRepository(db)
        replay = await repository.persist_audio_upload(
            session_id="session-1",
            attempt_id="attempt-1",
            upload_id="upload-1",
            declared_sha256=digest,
            staged=_stage(replay_path, body),
            destination=destination,
        )
        await repository.commit_audio_upload()

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
    async with repository_database() as db:
        repository = ConversationalSessionRepository(db)
        await repository.persist_audio_upload(
            session_id="session-1",
            attempt_id="attempt-1",
            upload_id="upload-1",
            declared_sha256=hashlib.sha256(original).hexdigest(),
            staged=_stage(tmp_path / "first.tmp", original),
            destination=destination,
        )
        await repository.commit_audio_upload()

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
async def test_persist_replays_matching_receipt_after_winner_advances_attempt(
    tmp_path: Path,
) -> None:
    """A winner may commit after the initial receipt lookup but before the state fence."""
    body = b"winner-audio"
    digest = hashlib.sha256(body).hexdigest()
    destination = tmp_path / "media" / "session-1" / "attempt-1-upload-1.webm"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(body)
    attempt = SimpleNamespace(
        id="attempt-1",
        session_id="session-1",
        recording_type="audio",
        attempt_state="uploaded",
        audio_uri=str(destination),
        audio_content_hash=digest,
        audio_retention_policy="delete_after_processing",
        audio_retention_state="temporary",
    )
    receipt = SimpleNamespace(
        attempt_id="attempt-1",
        upload_id="upload-1",
        request_hash=_request_hash(content_sha256=digest, byte_size=len(body)),
        result_state="completed",
        content_sha256=digest,
        byte_size=len(body),
        mime_type="audio/webm",
        storage_uri=str(destination),
    )

    class WinnerCommittedBetweenReadsSession:
        def __init__(self) -> None:
            self.scalar_values = iter((None, attempt, receipt))

        async def scalar(self, _statement):
            return next(self.scalar_values)

        async def get(self, _model, _identifier):
            return SimpleNamespace(
                experience_version="conversational_v1",
                status="active",
                conversation_state="listening",
                active_recording_id="attempt-1",
                deletion_state="not_requested",
            )

    staged_path = tmp_path / "matching-replay.tmp"
    result = await ConversationalSessionRepository(
        WinnerCommittedBetweenReadsSession()
    ).persist_audio_upload(
        session_id="session-1",
        attempt_id="attempt-1",
        upload_id="upload-1",
        declared_sha256=digest,
        staged=_stage(staged_path, body),
        destination=destination,
    )

    assert result.result == "completed"
    assert result.content_sha256 == digest
    assert not staged_path.exists()


@pytest.mark.asyncio
async def test_persist_rejects_changed_receipt_after_winner_advances_attempt(
    tmp_path: Path,
) -> None:
    """Replaying the post-fence receipt without its hash fence accepts changed audio."""
    original = b"winner-audio"
    changed = b"changed-audio"
    original_digest = hashlib.sha256(original).hexdigest()
    changed_digest = hashlib.sha256(changed).hexdigest()
    destination = tmp_path / "media" / "session-1" / "attempt-1-upload-1.webm"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(original)
    attempt = SimpleNamespace(
        id="attempt-1",
        session_id="session-1",
        recording_type="audio",
        attempt_state="uploaded",
        audio_uri=str(destination),
        audio_content_hash=original_digest,
        audio_retention_policy="delete_after_processing",
        audio_retention_state="temporary",
    )
    receipt = SimpleNamespace(
        attempt_id="attempt-1",
        upload_id="upload-1",
        request_hash=_request_hash(
            content_sha256=original_digest, byte_size=len(original)
        ),
        result_state="completed",
        content_sha256=original_digest,
        byte_size=len(original),
        mime_type="audio/webm",
        storage_uri=str(destination),
    )

    class WinnerCommittedBetweenReadsSession:
        def __init__(self) -> None:
            self.scalar_values = iter((None, attempt, receipt))

        async def scalar(self, _statement):
            return next(self.scalar_values)

        async def get(self, _model, _identifier):
            return SimpleNamespace(
                experience_version="conversational_v1",
                status="active",
                conversation_state="listening",
                active_recording_id="attempt-1",
                deletion_state="not_requested",
            )

    staged_path = tmp_path / "changed-replay.tmp"
    with pytest.raises(
        ConversationalRepositoryError,
        match="coach_audio_upload_idempotency_conflict",
    ):
        await ConversationalSessionRepository(
            WinnerCommittedBetweenReadsSession()
        ).persist_audio_upload(
            session_id="session-1",
            attempt_id="attempt-1",
            upload_id="upload-1",
            declared_sha256=changed_digest,
            staged=_stage(staged_path, changed),
            destination=destination,
        )

    assert not staged_path.exists()


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
        def _fail_completed_receipt(
            _connection, _cursor, statement, _parameters, _context, _executemany
        ) -> None:
            if statement.startswith("UPDATE interview_attempt_uploads"):
                raise RuntimeError("injected database failure")

        event.listen(db.sync_session.bind, "before_cursor_execute", _fail_completed_receipt)
        try:
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
        finally:
            event.remove(
                db.sync_session.bind,
                "before_cursor_execute",
                _fail_completed_receipt,
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


@pytest.mark.asyncio
@pytest.mark.parametrize("same_body", [True, False], ids=["same", "changed"])
async def test_concurrent_upload_retries_never_overwrite_or_unlink_winner(
    repository_database, tmp_path: Path, same_body: bool
) -> None:
    """Publishing before the unique claim lets a loser destroy winner bytes."""
    await _seed_listening_attempt(repository_database)
    destination = tmp_path / "media" / "session-1" / "attempt-1-upload-1.webm"
    destination.parent.mkdir(parents=True)
    first_body = b"concurrent-original"
    second_body = first_body if same_body else b"concurrent-changed"

    async def upload(body: bytes, staged_name: str):
        async with repository_database() as db:
            repository = ConversationalSessionRepository(db)
            try:
                result = await repository.persist_audio_upload(
                    session_id="session-1",
                    attempt_id="attempt-1",
                    upload_id="upload-1",
                    declared_sha256=hashlib.sha256(body).hexdigest(),
                    staged=_stage(tmp_path / staged_name, body),
                    destination=destination,
                )
                await repository.commit_audio_upload()
                return result
            except ConversationalRepositoryError as error:
                await db.rollback()
                return error

    first, second = await asyncio.gather(
        upload(first_body, "concurrent-first.tmp"),
        upload(second_body, "concurrent-second.tmp"),
    )

    async with repository_database() as db:
        uploads = tuple((await db.scalars(select(InterviewAttemptUpload))).all())
    assert len(uploads) == 1
    assert destination.is_file()
    assert destination.read_bytes() == (
        first_body if uploads[0].content_sha256 == hashlib.sha256(first_body).hexdigest() else second_body
    )
    if same_body:
        assert not isinstance(first, Exception)
        assert not isinstance(second, Exception)
        assert first == second
    else:
        assert sum(isinstance(value, Exception) for value in (first, second)) == 1
        loser = first if isinstance(first, Exception) else second
        assert str(loser) == "coach_audio_upload_idempotency_conflict"


@pytest.mark.asyncio
async def test_stream_rejects_upload_temp_parent_symlink_swap(
    tmp_path: Path,
) -> None:
    """Following a swapped staging parent writes upload bytes outside the root."""
    root = tmp_path / "media"
    temp_dir = coach_upload_temp_dir(root)
    original_temp = root / ".uploads-original"
    temp_dir.rename(original_temp)
    outside = tmp_path / "outside-temp"
    outside.mkdir()
    temp_dir.symlink_to(outside, target_is_directory=True)
    upload = UploadFile(
        BytesIO(b"synthetic-webm"),
        filename="answer.webm",
        headers=Headers({"content-type": "audio/webm"}),
    )

    with pytest.raises(CoachMediaError, match="coach_attempt_upload_conflict"):
        await stream_audio_upload(upload, max_bytes=64, temp_dir=temp_dir)
    await upload.close()

    assert not list(outside.iterdir())


@pytest.mark.asyncio
async def test_persist_rejects_destination_parent_symlink_swap(
    repository_database, tmp_path: Path
) -> None:
    """Following a swapped destination parent publishes outside the media root."""
    await _seed_listening_attempt(repository_database)
    root = tmp_path / "media"
    destination = resolve_owned_audio_path(
        root, "session-1", "attempt-1", "upload-1", ".webm"
    )
    original_parent = root / "session-original"
    destination.parent.rename(original_parent)
    outside = tmp_path / "outside-destination"
    outside.mkdir()
    destination.parent.symlink_to(outside, target_is_directory=True)
    body = b"synthetic-webm"

    async with repository_database() as db:
        with pytest.raises(
            ConversationalRepositoryError,
            match="coach_attempt_upload_conflict",
        ):
            await ConversationalSessionRepository(db).persist_audio_upload(
                session_id="session-1",
                attempt_id="attempt-1",
                upload_id="upload-1",
                declared_sha256=hashlib.sha256(body).hexdigest(),
                staged=_stage(root / ".uploads-source", body),
                destination=destination,
            )

    assert not list(outside.iterdir())


@pytest.mark.asyncio
async def test_cleanup_retries_the_owned_inode_after_unlink_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Closing a failed lease makes a later cleanup silently leave its inode."""
    upload = UploadFile(
        BytesIO(b"synthetic-webm"),
        filename="answer.webm",
        headers=Headers({"content-type": "audio/webm"}),
    )
    staged = await stream_audio_upload(
        upload,
        max_bytes=64,
        temp_dir=coach_upload_temp_dir(tmp_path / "media"),
    )
    entry = staged._entry
    assert entry is not None
    original_unlink = os.unlink
    failed = False

    def fail_the_owned_unlink(name, *args, **kwargs):
        nonlocal failed
        if name == staged.temporary_path.name and not failed:
            failed = True
            raise OSError("/private/cleanup-target")
        return original_unlink(name, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", fail_the_owned_unlink)

    with pytest.raises(CoachMediaError, match="coach_attempt_upload_conflict"):
        cleanup_staged_audio(staged)
    assert staged.temporary_path.exists()
    assert entry.closed is False

    cleanup_staged_audio(staged)
    await upload.close()

    assert failed is True
    assert entry.closed is True
    assert not staged.temporary_path.exists()


@pytest.mark.asyncio
async def test_rollback_retries_transient_publication_unlink_before_surfacing_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Giving up after one transient unlink failure leaves a rolled-back file."""
    body = b"synthetic-webm"
    staged_path = tmp_path / "publication-retry.tmp"
    destination = tmp_path / "media" / "session-1" / "attempt-1-upload-1.webm"
    destination.parent.mkdir(parents=True)
    publication = publish_staged_audio(_stage(staged_path, body), destination)
    original_unlink = os.unlink
    unlink_attempts = 0

    def fail_destination_once(name, *args, **kwargs):
        nonlocal unlink_attempts
        if name == destination.name:
            unlink_attempts += 1
            if unlink_attempts == 1:
                raise OSError("/private/destination-target")
        return original_unlink(name, *args, **kwargs)

    class RolledBackSession:
        async def rollback(self) -> None:
            return None

    monkeypatch.setattr(os, "unlink", fail_destination_once)
    repository = ConversationalSessionRepository(RolledBackSession())
    repository._audio_publication = publication

    await repository._rollback_audio_upload()

    assert unlink_attempts == 2
    assert repository._audio_publication is None
    assert not destination.exists()


@pytest.mark.asyncio
async def test_rollback_never_unlinks_replacement_after_publication_unlink_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A retry that ignores the retained inode identity can delete a replacement."""
    body = b"synthetic-webm"
    staged_path = tmp_path / "publication-replacement.tmp"
    destination = tmp_path / "media" / "session-1" / "attempt-1-upload-1.webm"
    destination.parent.mkdir(parents=True)
    publication = publish_staged_audio(_stage(staged_path, body), destination)
    published_fd = publication._file_descriptor
    published = os.fstat(published_fd)
    assert published.st_ino == destination.stat().st_ino
    original_unlink = os.unlink
    swapped = False

    def replace_then_fail(name, *args, **kwargs):
        nonlocal swapped
        if name == destination.name and not swapped:
            swapped = True
            original_unlink(name, *args, **kwargs)
            replacement_fd = os.open(
                destination.name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=kwargs["dir_fd"],
            )
            with os.fdopen(replacement_fd, "wb") as replacement:
                replacement.write(b"replacement")
            raise OSError("/private/destination-target")
        return original_unlink(name, *args, **kwargs)

    class RolledBackSession:
        async def rollback(self) -> None:
            return None

    monkeypatch.setattr(os, "unlink", replace_then_fail)
    repository = ConversationalSessionRepository(RolledBackSession())
    repository._audio_publication = publication

    with pytest.raises(ConversationalRepositoryError, match="coach_attempt_upload_conflict"):
        await repository._rollback_audio_upload()

    assert swapped is True
    assert os.fstat(published_fd).st_ino == published.st_ino
    assert destination.read_bytes() == b"replacement"
    publication.release()


@pytest.mark.asyncio
async def test_cancelled_rollback_compensates_published_audio_before_propagating(
    tmp_path: Path,
) -> None:
    """Propagating cancellation before compensation leaves the published inode."""
    body = b"synthetic-webm"
    staged_path = tmp_path / "cancelled-rollback.tmp"
    destination = tmp_path / "media" / "session-1" / "attempt-1-upload-1.webm"
    destination.parent.mkdir(parents=True)

    publication = publish_staged_audio(_stage(staged_path, body), destination)

    class CancelledRollbackSession:
        async def rollback(self) -> None:
            raise asyncio.CancelledError()

        async def close(self) -> None:
            return None

    repository = ConversationalSessionRepository(CancelledRollbackSession())
    repository._audio_publication = publication

    with pytest.raises(asyncio.CancelledError):
        await repository._rollback_audio_upload()

    assert not staged_path.exists()
    assert not destination.exists()


@pytest.mark.asyncio
async def test_commit_keeps_durable_upload_success_when_lease_release_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reporting a release error as failure contradicts an already committed receipt."""
    body = b"synthetic-webm"
    destination = tmp_path / "media" / "session-1" / "attempt-1-upload-1.webm"
    destination.parent.mkdir(parents=True)
    publication = publish_staged_audio(
        _stage(tmp_path / "release-failure.tmp", body), destination
    )
    committed = False

    class DurableSession:
        async def commit(self) -> None:
            nonlocal committed
            committed = True

    def fail_release(_publication) -> None:
        raise CoachMediaError("coach_attempt_upload_conflict")

    monkeypatch.setattr(OwnedAudioPublication, "release", fail_release)
    repository = ConversationalSessionRepository(DurableSession())
    repository._audio_publication = publication

    await repository.commit_audio_upload()

    assert committed is True
    assert destination.read_bytes() == body


@pytest.mark.asyncio
async def test_rollback_failure_closes_session_and_surfaces_sanitized_error(
    repository_database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Swallowing rollback failure leaves an inactive transaction attached."""
    await _seed_listening_attempt(repository_database)
    body = b"synthetic-webm"
    digest = hashlib.sha256(body).hexdigest()
    destination = tmp_path / "media" / "session-1" / "attempt-1-upload-1.webm"
    destination.parent.mkdir(parents=True)

    async with repository_database() as db:
        def _fail_completed_receipt(
            _connection, _cursor, statement, _parameters, _context, _executemany
        ) -> None:
            if statement.startswith("UPDATE interview_attempt_uploads"):
                raise RuntimeError("injected database failure")

        async def _fail_rollback() -> None:
            raise OSError("/private/rollback-target")

        monkeypatch.setattr(db, "rollback", _fail_rollback)
        event.listen(db.sync_session.bind, "before_cursor_execute", _fail_completed_receipt)
        try:
            with pytest.raises(ConversationalRepositoryError) as raised:
                await ConversationalSessionRepository(db).persist_audio_upload(
                    session_id="session-1",
                    attempt_id="attempt-1",
                    upload_id="upload-1",
                    declared_sha256=digest,
                    staged=_stage(tmp_path / "rollback-failure.tmp", body),
                    destination=destination,
                )
        finally:
            event.remove(
                db.sync_session.bind,
                "before_cursor_execute",
                _fail_completed_receipt,
            )
        assert not db.in_transaction()

    assert str(raised.value) == "coach_attempt_upload_conflict"
    assert "/private" not in str(raised.value)
