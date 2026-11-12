"""RED contract for P6: the source_events hook (spec §5.3, AC29).

Written by Claude Code before implementation (plan §1.5). File-backed SQLite with
foreign keys on; the listeners here are test doubles, the source domains are real.
All data is synthetic.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import database
from app.config import settings
from app.database import Base, create_sqlite_engine
from app.models.coach_session import InterviewSession, SessionRecording
from app.models.question_bank import QuestionBankItem
from app.models.story import Story
from app.repositories.conversational_session_repository import (
    ConversationalSessionRepository,
)
from app.repositories.story_repository import StoryRepository
from app.schemas.coach_conversation import HardDeletionCommandRequest
from app.schemas.question_bank import QuestionBankUpdate
from app.schemas.story import StoryUpdate
from app.services import question_bank
from app.services.coach_privacy import CoachPrivacyService, TranscriptDeletionClaim
from app.services.source_events import (
    SourceChange,
    notify,
    register_listener,
    unregister_listener,
)

AUDIO = b"synthetic hook audio"


class ListenerFailed(RuntimeError):
    """Raised by the failing test listener."""


class RecordingListener:
    def __init__(self) -> None:
        self.calls: list[tuple[AsyncSession, SourceChange, bool]] = []

    async def on_source_change(self, session: AsyncSession, change: SourceChange) -> None:
        self.calls.append((session, change, session.in_transaction()))


class FailingListener:
    def __init__(self) -> None:
        self.calls = 0

    async def on_source_change(self, session: AsyncSession, change: SourceChange) -> None:
        self.calls += 1
        raise ListenerFailed("synthetic listener failure")


@pytest_asyncio.fixture
async def factory(tmp_path, monkeypatch):
    engine = create_sqlite_engine(f"sqlite+aiosqlite:///{tmp_path / 'hooks.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", str(tmp_path / "media"))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield session_factory
    finally:
        await engine.dispose()


@pytest.fixture
def listen():
    registered = []

    def _register(listener):
        register_listener(listener)
        registered.append(listener)
        return listener

    yield _register
    for listener in registered:
        unregister_listener(listener)


def _session(session_id: str) -> InterviewSession:
    return InterviewSession(
        id=session_id,
        company_name="Synthetic Ltd",
        role_title="Delivery Lead",
        config={},
        status="completed",
        conversation_state="completed",
        experience_version="conversational_v1",
        compatibility_key=f"key-{session_id}",
        activity_version=2,
        state_version=2,
        completed_at=datetime(2026, 11, 1, 9, 0),
    )


async def _seed_session_with_audio(factory, session_id: str) -> Path:
    media = Path(settings.HATCH_COACH_MEDIA_ROOT) / session_id / "answer.webm"
    media.parent.mkdir(parents=True, exist_ok=True)
    media.write_bytes(AUDIO)
    async with factory() as db:
        db.add(_session(session_id))
        await db.flush()
        db.add(
            SessionRecording(
                id=f"{session_id}-attempt",
                session_id=session_id,
                recording_type="audio",
                attempt_state="completed",
                transcript="Synthetic transcript kept on rollback",
                audio_uri=str(media),
                audio_content_hash=hashlib.sha256(AUDIO).hexdigest(),
                audio_retention_state="retained",
            )
        )
        await db.commit()
    return media


async def _seed_story_and_item(factory) -> None:
    async with factory() as db:
        db.add(
            Story(
                id="hook-story",
                title="Rescued a late delivery",
                slug="rescued-a-late-delivery",
                situation="Synthetic situation",
                result="Synthetic result",
            )
        )
        db.add(
            QuestionBankItem(
                id="hook-item",
                type="behavioural",
                title="Tell me about a rescue",
                question="Tell me about a delivery you rescued.",
                answer_draft="Synthetic draft",
            )
        )
        await db.commit()


async def test_notify_runs_listeners_in_callers_transaction(factory, listen) -> None:
    listener = listen(RecordingListener())
    await _seed_story_and_item(factory)

    async with factory() as db:
        await db.execute(text("UPDATE stories SET title = 'Uncommitted title' WHERE id = 'hook-story'"))
        change = SourceChange(kind="story", source_id="hook-story", change="edited")
        await notify(db, change)

        assert len(listener.calls) == 1
        seen_session, seen_change, in_transaction = listener.calls[0]
        assert seen_session is db
        assert seen_change == change
        assert in_transaction is True
        # notify neither commits nor ends the caller's transaction.
        assert db.in_transaction()
        async with factory() as other:
            title = await other.scalar(text("SELECT title FROM stories WHERE id = 'hook-story'"))
        assert title == "Rescued a late delivery"
        await db.rollback()

    # Every §5.3 call site reports its change through notify, with the caller's session.
    listener.calls.clear()
    async with factory() as db:
        await StoryRepository(db).update("hook-story", StoryUpdate(title="Edited synthetic story"))
        await StoryRepository(db).soft_delete("hook-story")
        await question_bank.update_question_bank_item(
            db, "hook-item", QuestionBankUpdate(title="Edited synthetic item")
        )
        await question_bank.archive_question_bank_item(db, "hook-item")
        assert all(seen is db for seen, _, _ in listener.calls)
        await db.commit()
    assert [change for _, change, _ in listener.calls] == [
        SourceChange(kind="story", source_id="hook-story", change="edited"),
        SourceChange(kind="story", source_id="hook-story", change="deleted"),
        SourceChange(kind="question_bank_item", source_id="hook-item", change="edited"),
        SourceChange(kind="question_bank_item", source_id="hook-item", change="deleted"),
    ]


async def test_listener_error_rolls_back_source_change(factory, listen) -> None:
    await _seed_story_and_item(factory)
    await _seed_session_with_audio(factory, "rollback-session")
    failing = listen(FailingListener())

    async def attempt(operation) -> None:
        async with factory() as db:
            with pytest.raises(ListenerFailed):
                await operation(db)
            await db.rollback()

    await attempt(lambda db: StoryRepository(db).update("hook-story", StoryUpdate(title="Never saved")))
    await attempt(lambda db: StoryRepository(db).soft_delete("hook-story"))
    await attempt(
        lambda db: question_bank.update_question_bank_item(
            db, "hook-item", QuestionBankUpdate(title="Never saved")
        )
    )
    await attempt(lambda db: question_bank.archive_question_bank_item(db, "hook-item"))
    await attempt(
        lambda db: ConversationalSessionRepository(db).delete_attempt_transcript(
            TranscriptDeletionClaim(
                session_id="rollback-session",
                attempt_id="rollback-session-attempt",
                expected_attempt_version=0,
                expected_processing_generation=0,
                expected_state_version=2,
                expected_activity_version=2,
            )
        )
    )
    await attempt(
        lambda db: CoachPrivacyService(ConversationalSessionRepository(db)).claim_hard_deletion(
            "rollback-session",
            HardDeletionCommandRequest(
                command_id="rollback-delete",
                confirmation="DELETE",
                contract_version="coach_session_hard_delete_v1",
            ),
            now=datetime.utcnow(),
        )
    )
    assert failing.calls == 6

    async with factory() as db:
        story = await db.get(Story, "hook-story")
        item = await db.get(QuestionBankItem, "hook-item")
        session = await db.get(InterviewSession, "rollback-session")
        recording = await db.get(SessionRecording, "rollback-session-attempt")
        assert (story.title, story.version, story.is_active) == ("Rescued a late delivery", 1, True)
        assert (item.title, item.archived_at) == ("Tell me about a rescue", None)
        assert session.deletion_state == "not_requested"
        assert session.activity_version == 2
        assert recording.transcript == "Synthetic transcript kept on rollback"
        assert recording.attempt_state == "completed"


async def test_notify_runs_before_media_removal(factory, listen) -> None:
    # delete_attempt_transcript: a failing listener leaves the audio file in place.
    transcript_media = await _seed_session_with_audio(factory, "media-transcript")
    failing = listen(FailingListener())
    async with factory() as db:
        with pytest.raises(ListenerFailed):
            await ConversationalSessionRepository(db).delete_attempt_transcript(
                TranscriptDeletionClaim(
                    session_id="media-transcript",
                    attempt_id="media-transcript-attempt",
                    expected_attempt_version=0,
                    expected_processing_generation=0,
                    expected_state_version=2,
                    expected_activity_version=2,
                )
            )
        await db.rollback()
    assert failing.calls == 1
    assert transcript_media.read_bytes() == AUDIO
    async with factory() as db:
        recording = await db.get(SessionRecording, "media-transcript-attempt")
        assert recording.audio_uri == str(transcript_media)
        assert recording.audio_retention_state == "retained"

    # finalise_hard_deletion: claim succeeds (listener removed), then a failing
    # listener at finalise leaves the audio file and the session row in place.
    unregister_listener(failing)
    hard_media = await _seed_session_with_audio(factory, "media-hard")
    async with factory() as db:
        claim = await CoachPrivacyService(ConversationalSessionRepository(db)).claim_hard_deletion(
            "media-hard",
            HardDeletionCommandRequest(
                command_id="media-hard-delete",
                confirmation="DELETE",
                contract_version="coach_session_hard_delete_v1",
            ),
            now=datetime.utcnow(),
        )
        await db.commit()
    finalise_failing = listen(FailingListener())
    async with factory() as db:
        with pytest.raises(ListenerFailed):
            await ConversationalSessionRepository(db).finalise_hard_deletion(
                claim, datetime.utcnow()
            )
        await db.rollback()
    assert finalise_failing.calls == 1
    assert hard_media.read_bytes() == AUDIO
    async with factory() as db:
        session = await db.get(InterviewSession, "media-hard")
        assert session is not None
        assert session.deletion_state == "deleting"
