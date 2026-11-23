"""RED contract for P6: generation fencing at finalise and dedupe (§10, §7.8, §8.6).

Written by Claude Code before implementation (plan §1.5). finalise_generation is
the §10.1 interface; sources change through the real domain methods; every
assertion reloads durable rows. Only the local model server is faked, at HTTP.
All data is synthetic.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.models.coach_session import InterviewSession
from app.models.story import Story
from app.repositories.coach_readiness_repository import CoachReadinessRepository
from app.repositories.conversational_session_repository import (
    ConversationalSessionRepository,
)
from app.repositories.story_repository import StoryRepository
from app.services.coach_privacy import CoachPrivacyService
from app.services.coach_privacy_queue import _process_hard_deletion
from app.services.coach_readiness.contracts import (
    GenerationRequest,
    SourceRef,
    ValidatedOutput,
    finalise_generation,
    input_fingerprint,
)
from app.services.coach_readiness.privacy import ReadinessPrivacy
from app.services.source_events import register_listener, unregister_listener
from coach_readiness_support import (
    SUPPORTING,
    TIPS,
    client_for,
    configure_local_ai,
    derived_count,
    fake_llama,
    model_dispatches,
    not_the_test_client,
    readiness_app,
    request_tips,
    seed_pattern_sessions,
    explained_fingerprint,
    wait_for_operation,
)
from test_coach_report_privacy_flow import deletion_request

NOW = datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc)
EXPLAIN = "coach.readiness.explain"
BRIEF = "coach.readiness.brief_enhance"


@pytest.fixture
def readiness_listener(coach_database):
    listener = ReadinessPrivacy(CoachReadinessRepository(coach_database))
    register_listener(listener)
    try:
        yield listener
    finally:
        unregister_listener(listener)


def _request(task_id: str, kind: str, cache_key: str, sources: list[SourceRef]) -> GenerationRequest:
    return GenerationRequest(
        task_id=task_id,
        kind=kind,
        cache_key=cache_key,
        input_fingerprint=input_fingerprint(task_id, sources),
        sources=tuple(sources),
    )


def _output() -> ValidatedOutput:
    return ValidatedOutput(
        text_json={"tips": ["Synthetic grounded tip."]},
        model_identity="qwen3.5-4b-q4km-primary",
        prompt_version="explain-v1",
    )


async def _session_ref(factory, session_id: str) -> SourceRef:
    async with factory() as db:
        session = await db.get(InterviewSession, session_id)
        return SourceRef(
            kind="coach_session", source_id=session_id, version=str(session.activity_version)
        )


async def _finalise(factory, request: GenerationRequest):
    async with factory() as db:
        outcome = await finalise_generation(db, request, _output(), NOW)
        await db.commit()
    return outcome


async def _rows_for_cache_key(factory, cache_key: str) -> int:
    async with factory() as db:
        return int(
            (
                await db.execute(
                    text("SELECT count(*) FROM coach_derived_text WHERE cache_key = :key"),
                    {"key": cache_key},
                )
            ).scalar_one()
        )


async def test_session_deleted_mid_generation_is_fenced(coach_database, readiness_listener) -> None:
    await seed_pattern_sessions(coach_database)
    session_a, session_b = SUPPORTING
    sources = [
        await _session_ref(coach_database, session_a),
        await _session_ref(coach_database, session_b),
    ]
    earlier = await _finalise(coach_database, _request(EXPLAIN, "explain", "earlier", sources))
    assert earlier.status == "succeeded"
    assert await derived_count(coach_database, source_id=session_a) == 1

    # A generation starts from these sources; hard deletion is claimed while it runs.
    running = _request(EXPLAIN, "explain", "running", sources)
    async with coach_database() as db:
        claim = await CoachPrivacyService(ConversationalSessionRepository(db)).claim_hard_deletion(
            session_a, deletion_request("p6-fence"), now=datetime.utcnow()
        )
        await db.commit()
    assert await derived_count(coach_database, source_id=session_a) == 0

    outcome = await _finalise(coach_database, running)
    assert outcome.status == "fenced"
    assert await _rows_for_cache_key(coach_database, "running") == 0

    await _process_hard_deletion(claim)
    async with coach_database() as db:
        assert await db.get(InterviewSession, session_a) is None
        cited = await db.execute(
            text("SELECT count(*) FROM coach_derived_sources WHERE source_id = :id"),
            {"id": session_a},
        )
        assert cited.scalar_one() == 0
    assert await derived_count(coach_database) == 0


async def test_activity_version_change_fences_generation(coach_database) -> None:
    await seed_pattern_sessions(coach_database)
    session_a, session_b = SUPPORTING
    sources = [
        await _session_ref(coach_database, session_a),
        await _session_ref(coach_database, session_b),
    ]

    current = await _finalise(coach_database, _request(EXPLAIN, "explain", "current", sources))
    assert current.status == "succeeded"
    async with coach_database() as db:
        written = (
            await db.execute(
                text(
                    "SELECT t.kind, s.source_kind, s.source_id, s.source_version "
                    "FROM coach_derived_text t JOIN coach_derived_sources s "
                    "ON s.derived_text_id = t.id WHERE t.cache_key = 'current' "
                    "ORDER BY s.source_id"
                )
            )
        ).all()
    assert [tuple(row) for row in written] == [
        ("explain", "coach_session", session_a, "1"),
        ("explain", "coach_session", session_b, "1"),
    ]

    # New Phase 1 activity on a supporting session after the request was built.
    stale = _request(EXPLAIN, "explain", "stale", sources)
    async with coach_database() as db:
        await db.execute(
            text(
                "UPDATE interview_sessions SET activity_version = activity_version + 1 "
                "WHERE id = :id"
            ),
            {"id": session_b},
        )
        await db.commit()

    outcome = await _finalise(coach_database, stale)
    assert outcome.status == "fenced"
    assert await _rows_for_cache_key(coach_database, "stale") == 0
    async with coach_database() as db:
        sources_for_stale = await db.execute(
            text(
                "SELECT count(*) FROM coach_derived_sources s "
                "LEFT JOIN coach_derived_text t ON t.id = s.derived_text_id "
                "WHERE t.id IS NULL OR t.cache_key = 'stale'"
            )
        )
        assert sources_for_stale.scalar_one() == 0


async def test_generation_after_story_soft_delete_is_fenced(coach_database, readiness_listener) -> None:
    async with coach_database() as db:
        db.add(Story(id="fenced-story", title="Synthetic fenced story", slug="fenced-story", result="Done"))
        await db.commit()
        story = await db.get(Story, "fenced-story")
        sources = [SourceRef(kind="story", source_id="fenced-story", version=str(story.version))]
    request = _request(BRIEF, "brief", "after-soft-delete", sources)

    async with coach_database() as db:
        assert await StoryRepository(db).soft_delete("fenced-story") is True
        await db.commit()

    outcome = await _finalise(coach_database, request)
    assert outcome.status == "fenced"
    assert await _rows_for_cache_key(coach_database, "after-soft-delete") == 0
    assert await derived_count(coach_database, source_id="fenced-story") == 0


@pytest.mark.httpx_mock(should_mock=not_the_test_client)
async def test_same_fingerprint_dedupes_to_one_generation(
    coach_database, readiness_listener, httpx_mock, tmp_path, monkeypatch
) -> None:
    configure_local_ai(tmp_path, monkeypatch)
    fake_llama(httpx_mock, delay=0.3)
    await seed_pattern_sessions(coach_database)

    async with client_for(readiness_app(coach_database)) as client:
        fingerprint = await explained_fingerprint(client)
        first, second = await asyncio.gather(
            request_tips(client, fingerprint), request_tips(client, fingerprint)
        )
        accepted = [item for item in (first, second) if item.status_code == 202]
        assert accepted, (first.text, second.text)
        assert all(item.status_code in (200, 202) for item in (first, second))
        operation_ids = {item.json()["operation_id"] for item in accepted}
        assert len(operation_ids) == 1
        finished = await wait_for_operation(client, operation_ids.pop())
        assert finished["status"] == "succeeded"

        cached = await request_tips(client, fingerprint)
        assert cached.status_code == 200, cached.text
        assert cached.json()["tips"] == TIPS

    assert len(model_dispatches(httpx_mock)) == 1
    assert await derived_count(coach_database, kind="explain") == 1
