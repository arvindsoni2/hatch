"""RED contract for P6: derived-text cascade through source_events (§5.3, §7.8).

Written by Claude Code before implementation (plan §1.5). The readiness listener
is the real ReadinessPrivacy registered as main.py would; every source change goes
through the existing domain method. Assertions read durable rows from a fresh
session. All data is synthetic.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.models.coach_session import InterviewSession
from app.models.question_bank import QuestionBankItem
from app.models.story import Story
from app.repositories.coach_readiness_repository import CoachReadinessRepository
from app.repositories.conversational_session_repository import (
    ConversationalSessionRepository,
)
from app.repositories.story_repository import StoryRepository
from app.schemas.question_bank import QuestionBankUpdate
from app.schemas.story import StoryUpdate
from app.services import question_bank
from app.services.coach_privacy import CoachPrivacyService, TranscriptDeletionClaim
from app.services.coach_privacy_queue import _process_hard_deletion
from app.services.coach_readiness.privacy import ReadinessPrivacy
from app.services.source_events import register_listener, unregister_listener
from coach_readiness_support import (
    SUPPORTING,
    client_for,
    configure_local_ai,
    derived_count,
    fake_llama,
    insert_derived_text,
    model_dispatches,
    not_the_test_client,
    readiness_app,
    request_tips,
    seed_pattern_sessions,
    explained_fingerprint,
    wait_for_operation,
)
from test_coach_report_privacy_flow import deletion_request


@pytest.fixture
def readiness_listener(coach_database):
    listener = ReadinessPrivacy(CoachReadinessRepository(coach_database))
    register_listener(listener)
    try:
        yield listener
    finally:
        unregister_listener(listener)


async def _transcript_claim(factory, session_id: str) -> TranscriptDeletionClaim:
    async with factory() as db:
        session = await db.get(InterviewSession, session_id)
        return TranscriptDeletionClaim(
            session_id=session_id,
            attempt_id=f"{session_id}-attempt",
            expected_attempt_version=0,
            expected_processing_generation=0,
            expected_state_version=session.state_version,
            expected_activity_version=session.activity_version,
        )


async def test_transcript_delete_purges_derived_text(coach_database, readiness_listener) -> None:
    await seed_pattern_sessions(coach_database)
    session_a, session_b = SUPPORTING
    await insert_derived_text(
        coach_database, text_id="cites-a", kind="explain",
        sources=[("coach_session", session_a, "1"), ("coach_session", session_b, "1")],
    )
    await insert_derived_text(
        coach_database, text_id="cites-b-only", kind="explain",
        sources=[("coach_session", session_b, "1")],
    )

    claim = await _transcript_claim(coach_database, session_a)
    async with coach_database() as db:
        await ConversationalSessionRepository(db).delete_attempt_transcript(claim)
        await db.commit()

    assert await derived_count(coach_database, source_id=session_a) == 0
    assert await derived_count(coach_database) == 1
    assert await derived_count(coach_database, source_id=session_b) == 1


async def test_claim_purges_and_finalise_purges_again(coach_database, readiness_listener) -> None:
    await seed_pattern_sessions(coach_database)
    session_a, session_b = SUPPORTING
    await insert_derived_text(
        coach_database, text_id="before-claim", kind="brief",
        sources=[("coach_session", session_a, "1")],
    )
    await insert_derived_text(
        coach_database, text_id="unrelated", kind="explain",
        sources=[("coach_session", session_b, "1")],
    )

    async with coach_database() as db:
        claim = await CoachPrivacyService(ConversationalSessionRepository(db)).claim_hard_deletion(
            session_a, deletion_request("p6-claim"), now=datetime.utcnow()
        )
        await db.commit()
    assert await derived_count(coach_database, source_id=session_a) == 0
    async with coach_database() as db:
        assert (await db.get(InterviewSession, session_a)).deletion_state == "deleting"

    # Text that reaches the table between claim and finalise is purged again.
    await insert_derived_text(
        coach_database, text_id="between", kind="explain",
        sources=[("coach_session", session_a, "1")],
    )
    await _process_hard_deletion(claim)

    async with coach_database() as db:
        assert await db.get(InterviewSession, session_a) is None
    assert await derived_count(coach_database, source_id=session_a) == 0
    assert await derived_count(coach_database) == 1


async def test_story_edit_and_soft_delete_purge_derived_text(
    coach_database, readiness_listener
) -> None:
    async with coach_database() as db:
        for story_id in ("story-edit", "story-delete", "story-other"):
            db.add(Story(id=story_id, title=f"Synthetic {story_id}", slug=story_id, result="Done"))
        await db.commit()
    for story_id in ("story-edit", "story-delete", "story-other"):
        await insert_derived_text(
            coach_database, text_id=f"text-{story_id}", kind="brief",
            sources=[("story", story_id, "1")],
        )

    async with coach_database() as db:
        await StoryRepository(db).update("story-edit", StoryUpdate(title="Synthetic edited"))
        await db.commit()
    assert await derived_count(coach_database, source_id="story-edit") == 0

    async with coach_database() as db:
        assert await StoryRepository(db).soft_delete("story-delete") is True
        await db.commit()
    assert await derived_count(coach_database, source_id="story-delete") == 0
    assert await derived_count(coach_database, source_id="story-other") == 1


async def test_qb_edit_and_archive_purge_derived_text(coach_database, readiness_listener) -> None:
    async with coach_database() as db:
        for item_id in ("item-edit", "item-archive", "item-other"):
            db.add(
                QuestionBankItem(
                    id=item_id, type="behavioural", title=f"Synthetic {item_id}",
                    question="Tell me about a synthetic rescue.", answer_draft="Draft",
                )
            )
        await db.commit()
    for item_id in ("item-edit", "item-archive", "item-other"):
        await insert_derived_text(
            coach_database, text_id=f"text-{item_id}", kind="brief",
            sources=[("question_bank_item", item_id, "v1")],
        )

    async with coach_database() as db:
        await question_bank.update_question_bank_item(
            db, "item-edit", QuestionBankUpdate(title="Synthetic edited")
        )
        await db.commit()
    assert await derived_count(coach_database, source_id="item-edit") == 0

    async with coach_database() as db:
        assert await question_bank.archive_question_bank_item(db, "item-archive") is True
        await db.commit()
    assert await derived_count(coach_database, source_id="item-archive") == 0
    assert await derived_count(coach_database, source_id="item-other") == 1


@pytest.mark.httpx_mock(should_mock=not_the_test_client)
async def test_supporting_session_edit_purges_tips(
    coach_database, readiness_listener, httpx_mock, tmp_path, monkeypatch
) -> None:
    configure_local_ai(tmp_path, monkeypatch)
    fake_llama(httpx_mock)
    await seed_pattern_sessions(coach_database)
    session_a, _ = SUPPORTING

    async with client_for(readiness_app(coach_database)) as client:
        fingerprint = await explained_fingerprint(client)
        first = await request_tips(client, fingerprint)
        assert first.status_code == 202, first.text
        assert (await wait_for_operation(client, first.json()["operation_id"]))["status"] == "succeeded"
        cached = await request_tips(client, fingerprint)
        assert cached.status_code == 200, cached.text
        assert len(model_dispatches(httpx_mock)) == 1
        assert await derived_count(coach_database, kind="explain", source_id=session_a) == 1

        claim = await _transcript_claim(coach_database, session_a)
        async with coach_database() as db:
            await ConversationalSessionRepository(db).delete_attempt_transcript(claim)
            await db.commit()

        assert await derived_count(coach_database, kind="explain") == 0
        # The cached tips are gone: the same request no longer returns them.
        after = await request_tips(client, fingerprint)
        assert after.status_code != 200, after.text
        if after.status_code == 202:
            await wait_for_operation(client, after.json()["operation_id"])
