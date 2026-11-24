"""RED contract for P9: What Hatch remembers, delete-all and the readiness journey.

Written by Claude Code before implementation (plan §1.5, spec §7.8, §10.1, §14,
AC24, AC25). The readiness listener is the real ReadinessPrivacy registered as
main.py does; routes run through the real ``get_db`` (which commits) against the
file-backed ``coach_database``. Every assertion reads durable rows from a fresh
session. All data is synthetic.

The memory kinds are the closed set of §7.8 rows, in page order (see P9-red.md,
"Assumed interfaces").
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.config import settings
from app.database import Base
from app.models.application import Application, InterviewRound
from app.models.coach_readiness import (
    CoachCompetencyOverride,
    CoachFocusArea,
    CoachInterviewBrief,
    CoachInterviewDebrief,
    CoachPatternDismissal,
    CoachPracticePlan,
)
from app.models.job import JobPosting
from app.models.job_score import JobScore
from app.models.question_bank import QuestionBankItem
from app.models.story import Story
from app.repositories.coach_readiness_repository import CoachReadinessRepository
from app.repositories.conversational_session_repository import (
    ConversationalSessionRepository,
)
from app.repositories.interview_repository import InterviewRepository
from app.repositories.story_repository import StoryRepository
from app.schemas.interview import InterviewRoundUpdate
from app.schemas.story import StoryUpdate
from app.services.coach_privacy import CoachPrivacyService
from app.services.coach_privacy_queue import _process_hard_deletion
from app.services.coach_readiness import brief as brief_service
from app.services.coach_readiness.privacy import ReadinessPrivacy
from app.services.source_events import register_listener, unregister_listener
from coach_readiness_support import (
    AUDIO_BYTES,
    CHAT_COMPLETIONS,
    READINESS,
    SUPPORTING,
    chat_completion,
    client_for,
    configure_local_ai,
    derived_count,
    explained_fingerprint,
    fake_llama,
    insert_derived_text,
    not_the_test_client,
    request_tips,
    seed_pattern_sessions,
    wait_for_operation,
)
from test_coach_report_privacy_flow import deletion_request

MEMORY = f"{READINESS}/memory"

# §7.8 rows that are stored, in page order. "Patterns" is derived and has no
# delete of its own (the page links to Coach sessions instead).
MEMORY_KINDS = (
    "dismissed_patterns",
    "focus_areas_and_plans",
    "briefs",
    "debriefs",
    "explain_tips",
    "competency_overrides",
)

# Every Phase 2 table (spec §11). Everything else in the schema is Phase 1 data.
PHASE2_TABLES = (
    "coach_pattern_dismissals",
    "coach_focus_areas",
    "coach_practice_plans",
    "coach_interview_briefs",
    "coach_interview_debriefs",
    "coach_derived_text",
    "coach_derived_sources",
    "coach_competency_overrides",
)

FLAGS = (
    "HATCH_COACH_READINESS_ENABLED",
    "HATCH_COACH_BRIEF_ENABLED",
    "HATCH_COACH_DEBRIEF_ENABLED",
    "HATCH_COACH_STORY_COVERAGE_ENABLED",
)

T0 = datetime(2026, 11, 2, 9, 0)  # naive UTC, as the §11 columns store it


@pytest.fixture
def readiness_listener(coach_database):
    listener = ReadinessPrivacy(CoachReadinessRepository(coach_database))
    register_listener(listener)
    try:
        yield listener
    finally:
        unregister_listener(listener)


@pytest.fixture
def ai_off(tmp_path, monkeypatch) -> Path:
    """An empty Hatch config dir: AI mode reads ``not_configured`` (AI off)."""
    config = tmp_path / "ai-off"
    config.mkdir()
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(config))
    return config


def _flags(monkeypatch, value: bool) -> None:
    for flag in FLAGS:
        monkeypatch.setattr(settings, flag, value)


def _app() -> FastAPI:
    """The readiness router on the real ``get_db`` (commits like production)."""
    from app.routers.coach_readiness import router

    app = FastAPI()
    app.include_router(router)
    return app


def _privacy(factory) -> ReadinessPrivacy:
    return ReadinessPrivacy(CoachReadinessRepository(factory))


def _utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def _table_count(factory, table: str) -> int:
    async with factory() as db:
        return int((await db.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one())


async def _phase2_counts(factory) -> dict[str, int]:
    return {table: await _table_count(factory, table) for table in PHASE2_TABLES}


async def _phase1_snapshot(factory) -> dict[str, list[tuple]]:
    """Every row of every non-Phase-2 table, in a stable order."""
    snapshot: dict[str, list[tuple]] = {}
    async with factory() as db:
        for table in Base.metadata.sorted_tables:
            if table.name in PHASE2_TABLES:
                continue
            rows = (await db.execute(text(f"SELECT * FROM {table.name}"))).all()
            snapshot[table.name] = sorted((tuple(row) for row in rows), key=repr)
    return snapshot


async def _round_questions(factory, round_id: str) -> list[str] | None:
    async with factory() as db:
        row = await db.get(InterviewRound, round_id)
        return row.questions_asked


# --------------------------------------------------------------------------
# Synthetic seed: known rows for every memory kind, plus Phase 1 neighbours.
# --------------------------------------------------------------------------

EXPECTED_COUNTS = {
    "dismissed_patterns": 2,
    "focus_areas_and_plans": 3,  # 2 focus areas + 1 plan
    "briefs": 1,                 # cached brief text, not brief state rows
    "debriefs": 2,
    "explain_tips": 2,
    "competency_overrides": 3,
}
EXPECTED_LAST = {
    "dismissed_patterns": T0 + timedelta(hours=2),
    "focus_areas_and_plans": T0 + timedelta(hours=7),
    "briefs": T0 + timedelta(hours=9),
    "debriefs": T0 + timedelta(hours=12),
    "explain_tips": T0 + timedelta(hours=15),
    "competency_overrides": T0 + timedelta(hours=18),
}


async def _seed_every_kind(factory) -> None:
    async with factory() as db:
        db.add(JobPosting(
            id="mem-job", title="Delivery Lead", company="Synthetic Energy",
            url="https://example.test/mem", source="synthetic",
            description="Lead delivery across four teams.",
        ))
        await db.flush()
        db.add(Application(id="mem-app", job_id="mem-job", status="interview", priority="normal"))
        await db.flush()
        for number, (round_id, questions) in enumerate(
            (
                ("mem-round-1", ["Synthetic question one", "Typed before the debrief"]),
                ("mem-round-2", ["Round two question"]),
                ("mem-round-3", ["Keep me, no debrief here"]),
            ),
            start=1,
        ):
            db.add(InterviewRound(
                id=round_id, application_id="mem-app", round_number=number,
                type="behavioural", scheduled_at=T0 - timedelta(days=number),
                duration_minutes=60, status="completed", questions_asked=questions,
            ))
        await db.flush()

        db.add(CoachPatternDismissal(fingerprint="sha256:dismissed-1", dismissed_at=T0 + timedelta(hours=1)))
        db.add(CoachPatternDismissal(fingerprint="sha256:dismissed-2", dismissed_at=T0 + timedelta(hours=2)))

        db.add(CoachFocusArea(
            id="mem-focus-1", status="active", active_slot=1, title="Make answers specific",
            dimension="specificity", criteria_json=[{"kind": "practice", "count": 1}],
            created_at=T0, updated_at=T0 + timedelta(hours=3),
        ))
        db.add(CoachFocusArea(
            id="mem-focus-2", status="archived", active_slot=None, title="Shorter answers",
            dimension="concision", criteria_json=[{"kind": "practice", "count": 1}],
            created_at=T0, updated_at=T0 + timedelta(hours=7),
        ))
        db.add(CoachPracticePlan(
            id="mem-plan", status="draft", minutes=30, items_json=[],
            created_at=T0, updated_at=T0 + timedelta(hours=5),
        ))
        await db.flush()

        db.add(CoachInterviewDebrief(
            id="mem-debrief-1", interview_round_id="mem-round-1", version=1, status="saved",
            overall=4, questions_json=[], proposals_json=[],
            notes_text="Synthetic rough notes.",
            created_at=T0, updated_at=T0 + timedelta(hours=12),
        ))
        db.add(CoachInterviewDebrief(
            id="mem-debrief-2", interview_round_id="mem-round-2", version=1, status="draft",
            overall=None, questions_json=[], proposals_json=[],
            created_at=T0, updated_at=T0 + timedelta(hours=10),
        ))

        for index in range(3):
            db.add(CoachCompetencyOverride(
                id=f"mem-override-{index}", application_id="mem-app",
                original=f"synthetic competency {index}", hidden=index == 2,
                created_at=T0, updated_at=T0 + timedelta(hours=16 + index),
            ))
        await db.commit()

    # Cached model text (spec §11 columns only). The competency cache is P8's
    # job-description extraction: it belongs to no §7.8 kind, so it is never
    # counted under briefs or explain tips; delete-all still removes it.
    for text_id, kind, created_at, sources in (
        ("mem-brief-text", "brief", T0 + timedelta(hours=9), [("interview_round", "mem-round-1", "1")]),
        ("mem-explain-1", "explain", T0 + timedelta(hours=14), [("coach_session", "mem-session", "1")]),
        ("mem-explain-2", "explain", T0 + timedelta(hours=15), [("coach_session", "mem-session", "1")]),
        ("mem-competency", "competency", T0 + timedelta(hours=20), [("job", "mem-job", "1")]),
    ):
        await insert_derived_text(factory, text_id=text_id, kind=kind, sources=sources)
        async with factory() as db:
            await db.execute(
                text("UPDATE coach_derived_text SET created_at = :at WHERE id = :id"),
                {"at": created_at, "id": text_id},
            )
            await db.commit()
    async with factory() as db:
        db.add(CoachInterviewBrief(
            id="mem-brief", interview_round_id="mem-round-1", enhancement_state="current",
            enhancement_fingerprint="sha256:mem", enhanced_text_id="mem-brief-text",
            created_at=T0, updated_at=T0 + timedelta(hours=9),
        ))
        await db.commit()


# --------------------------------------------------------------------------
# Named tests (plan P9)
# --------------------------------------------------------------------------


async def test_inventory_counts_match_rows(coach_database, ai_off, monkeypatch) -> None:
    """Privacy page accuracy: one entry per §7.8 kind, true counts and last update."""
    _flags(monkeypatch, True)
    await _seed_every_kind(coach_database)

    inventory = await _privacy(coach_database).inventory()

    assert [item.kind for item in inventory.kinds] == list(MEMORY_KINDS)
    assert {item.kind: item.count for item in inventory.kinds} == EXPECTED_COUNTS
    assert {item.kind: _utc(item.last_updated) for item in inventory.kinds} == {
        kind: _utc(value) for kind, value in EXPECTED_LAST.items()
    }

    async with client_for(_app()) as client:
        response = await client.get(MEMORY)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["kind"] for item in body["kinds"]] == list(MEMORY_KINDS)
    assert {item["kind"]: item["count"] for item in body["kinds"]} == EXPECTED_COUNTS
    for item in body["kinds"]:
        assert item["last_updated"].endswith("Z"), item
        assert _utc(item["last_updated"]) == _utc(EXPECTED_LAST[item["kind"]])

    # An empty kind reports zero and no timestamp.
    deleted = await _privacy(coach_database).delete_kind("explain_tips")
    assert deleted == 2
    after = await _privacy(coach_database).inventory()
    explain = next(item for item in after.kinds if item.kind == "explain_tips")
    assert (explain.count, explain.last_updated) == (0, None)
    assert await derived_count(coach_database, kind="explain") == 0
    # Other kinds' rows are untouched by a per-kind delete.
    assert await derived_count(coach_database, kind="brief") == 1
    assert await derived_count(coach_database, kind="competency") == 1
    assert await _table_count(coach_database, "coach_interview_debriefs") == 2


async def test_delete_all_readiness_data_leaves_phase1(
    coach_database, readiness_listener, ai_off, monkeypatch
) -> None:
    """AC24: every Phase 2 row and cache goes; Phase 1 data is byte-for-byte untouched."""
    _flags(monkeypatch, True)
    await seed_pattern_sessions(coach_database)
    await _seed_every_kind(coach_database)
    async with coach_database() as db:
        db.add(Story(id="mem-story", title="Synthetic rescue", slug="mem-story", result="Done"))
        db.add(QuestionBankItem(
            id="mem-item", type="behavioural", title="Synthetic question",
            question="Tell me about a synthetic rescue.", answer_draft="Draft",
        ))
        await db.commit()
    assert all(count > 0 for count in (await _phase2_counts(coach_database)).values())
    phase1_before = await _phase1_snapshot(coach_database)

    result = await _privacy(coach_database).delete_all()

    assert await _phase2_counts(coach_database) == {table: 0 for table in PHASE2_TABLES}
    assert set(result.removed) == set(MEMORY_KINDS)
    assert result.removed == EXPECTED_COUNTS
    assert await _phase1_snapshot(coach_database) == phase1_before
    # Round questions are Phase 1 data: delete-all never clears them.
    assert await _round_questions(coach_database, "mem-round-1") == [
        "Synthetic question one", "Typed before the debrief",
    ]
    for session_id in SUPPORTING:
        media = Path(settings.HATCH_COACH_MEDIA_ROOT) / session_id / "answer.webm"
        assert media.read_bytes() == AUDIO_BYTES

    # The route does the same and is idempotent on an empty store.
    await _seed_every_kind_again(coach_database)
    async with client_for(_app()) as client:
        response = await client.delete(MEMORY)
        assert response.status_code == 200, response.text
        assert response.json()["removed"] == EXPECTED_COUNTS
        again = await client.delete(MEMORY)
        assert again.status_code == 200, again.text
        assert again.json()["removed"] == {kind: 0 for kind in MEMORY_KINDS}
    assert await _phase2_counts(coach_database) == {table: 0 for table in PHASE2_TABLES}
    assert await _phase1_snapshot(coach_database) == phase1_before


async def _seed_every_kind_again(factory) -> None:
    """Re-create the Phase 2 rows only (Phase 1 rows from the first seed remain)."""
    async with factory() as db:
        for table in PHASE2_TABLES:
            assert int((await db.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()) == 0
        db.add(CoachPatternDismissal(fingerprint="sha256:dismissed-1", dismissed_at=T0 + timedelta(hours=1)))
        db.add(CoachPatternDismissal(fingerprint="sha256:dismissed-2", dismissed_at=T0 + timedelta(hours=2)))
        db.add(CoachFocusArea(
            id="mem-focus-1", status="active", active_slot=1, title="Make answers specific",
            dimension="specificity", criteria_json=[{"kind": "practice", "count": 1}],
        ))
        db.add(CoachFocusArea(
            id="mem-focus-2", status="archived", active_slot=None, title="Shorter answers",
            dimension="concision", criteria_json=[{"kind": "practice", "count": 1}],
        ))
        db.add(CoachPracticePlan(id="mem-plan", status="draft", minutes=30, items_json=[]))
        db.add(CoachInterviewDebrief(
            id="mem-debrief-1", interview_round_id="mem-round-1", status="saved", overall=4,
        ))
        db.add(CoachInterviewDebrief(
            id="mem-debrief-2", interview_round_id="mem-round-2", status="draft",
        ))
        for index in range(3):
            db.add(CoachCompetencyOverride(
                id=f"mem-override-{index}", application_id="mem-app",
                original=f"synthetic competency {index}",
            ))
        await db.commit()
    await insert_derived_text(
        factory, text_id="mem-brief-text", kind="brief",
        sources=[("interview_round", "mem-round-1", "1")],
    )
    for text_id in ("mem-explain-1", "mem-explain-2"):
        await insert_derived_text(
            factory, text_id=text_id, kind="explain",
            sources=[("coach_session", SUPPORTING[1], "1")],
        )
    await insert_derived_text(
        factory, text_id="mem-competency", kind="competency",
        sources=[("job", "mem-job", "1")],
    )
    async with factory() as db:
        db.add(CoachInterviewBrief(
            id="mem-brief", interview_round_id="mem-round-1", enhancement_state="current",
            enhanced_text_id="mem-brief-text",
        ))
        await db.commit()


@pytest.mark.httpx_mock(should_mock=not_the_test_client)
async def test_flags_off_reads_and_deletes_work(
    coach_database, readiness_listener, ai_off, monkeypatch, httpx_mock
) -> None:
    """AC25: flags off → no new briefs, plans or generations; reads and deletes work."""
    await seed_pattern_sessions(coach_database)
    await _seed_every_kind(coach_database)
    configure_local_ai(ai_off.parent, monkeypatch)  # AI on: only the flags hold creation back
    fake_llama(httpx_mock)
    _flags(monkeypatch, False)
    async with coach_database() as db:
        db.add(InterviewRound(
            id="mem-round-future", application_id="mem-app", round_number=4,
            type="behavioural", scheduled_at=datetime.utcnow() + timedelta(days=3),
            duration_minutes=60, status="scheduled",
        ))
        await db.commit()
    before = await _phase2_counts(coach_database)

    async with client_for(_app()) as client:
        # Creation and new processing are refused.
        assert (await client.post(f"{READINESS}/plans", json={"minutes": 30})).status_code == 403
        focus = await client.post(f"{READINESS}/focus-areas", json={
            "title": "Blocked", "dimension": "specificity",
            "criteria": [{"kind": "practice", "count": 1}],
        })
        assert focus.status_code == 403
        brief = await client.get(f"{READINESS}/rounds/mem-round-future/brief")
        assert brief.status_code == 200, brief.text
        assert brief.json()["enhancement"]["state"] == "none"
        tips = await client.post(f"{READINESS}/rounds/mem-round-future/brief/tips")
        assert tips.status_code == 403
        await asyncio.gather(*brief_service._TASKS)
        assert await _phase2_counts(coach_database) == before
        assert [r for r in httpx_mock.get_requests() if r.method == "POST"] == []

        # Reads of existing rows work.
        focus_list = await client.get(f"{READINESS}/focus-areas")
        assert focus_list.status_code == 200, focus_list.text
        assert {item["id"] for item in focus_list.json()["items"]} >= {"mem-focus-1"}
        debrief = await client.get(f"{READINESS}/rounds/mem-round-1/debrief")
        assert debrief.status_code == 200, debrief.text
        assert debrief.json()["status"] == "saved"

        # The privacy page and every delete work.
        inventory = await client.get(MEMORY)
        assert inventory.status_code == 200, inventory.text
        assert {item["kind"]: item["count"] for item in inventory.json()["kinds"]} == EXPECTED_COUNTS
        one = await client.delete(f"{MEMORY}/explain_tips")
        assert one.status_code == 200, one.text
        assert one.json() == {"kind": "explain_tips", "removed": 2}
        assert await derived_count(coach_database, kind="explain") == 0
        everything = await client.delete(MEMORY)
        assert everything.status_code == 200, everything.text
    assert await _phase2_counts(coach_database) == {table: 0 for table in PHASE2_TABLES}


async def test_debrief_delete_optionally_clears_round_questions(
    coach_database, ai_off, monkeypatch
) -> None:
    """§7.8: deleting debriefs keeps the round's questions unless asked to clear them."""
    _flags(monkeypatch, True)
    await _seed_every_kind(coach_database)

    removed = await _privacy(coach_database).delete_kind("debriefs")

    assert removed == 2
    assert await _table_count(coach_database, "coach_interview_debriefs") == 0
    assert await _round_questions(coach_database, "mem-round-1") == [
        "Synthetic question one", "Typed before the debrief",
    ]
    assert await _round_questions(coach_database, "mem-round-2") == ["Round two question"]

    # Again with "also clear questions on the round", through the route.
    async with coach_database() as db:
        for debrief_id, round_id in (("mem-debrief-1", "mem-round-1"), ("mem-debrief-2", "mem-round-2")):
            db.add(CoachInterviewDebrief(
                id=debrief_id, interview_round_id=round_id, status="saved", overall=3,
            ))
        await db.commit()
    async with client_for(_app()) as client:
        response = await client.delete(
            f"{MEMORY}/debriefs", params={"clear_round_questions": "true"}
        )
    assert response.status_code == 200, response.text
    assert response.json() == {"kind": "debriefs", "removed": 2}
    assert await _table_count(coach_database, "coach_interview_debriefs") == 0
    assert not await _round_questions(coach_database, "mem-round-1")
    assert not await _round_questions(coach_database, "mem-round-2")
    # A round without a debrief keeps its questions.
    assert await _round_questions(coach_database, "mem-round-3") == ["Keep me, no debrief here"]
    # Rounds themselves are Phase 1 rows and stay.
    assert await _table_count(coach_database, "interview_rounds") == 3


# --------------------------------------------------------------------------
# Journey (plan P9)
# --------------------------------------------------------------------------

JOURNEY_STORY = "jrn-story"
JOURNEY_ROUND = "jrn-round"


def _brief_output(story_text: str) -> str:
    return json.dumps({
        "talking_points": [{"story_id": JOURNEY_STORY, "text": story_text}],
        "watch_outs": [],
    })


async def _seed_journey_round(factory) -> None:
    async with factory() as db:
        db.add(JobPosting(
            id="jrn-job", title="Delivery Lead", company="Synthetic Energy",
            url="https://example.test/jrn", source="synthetic",
            description="Lead delivery of the billing platform.",
        ))
        await db.flush()
        db.add(Application(id="jrn-app", job_id="jrn-job", status="interview", priority="normal"))
        db.add(JobScore(
            id="jrn-score", job_id="jrn-job", overall_score=0.9,
            keyword_matches=["delivery"], keyword_misses=[], scoring_method="local",
        ))
        db.add(Story(
            id=JOURNEY_STORY, title="Rescued a late delivery", slug=JOURNEY_STORY,
            situation="Synthetic situation", task="Synthetic task", action="Synthetic action",
            result="Delivered on time", tags=["delivery"], skills=["delivery"],
            metrics={"time": "2 weeks"},
        ))
        await db.flush()
        db.add(InterviewRound(
            id=JOURNEY_ROUND, application_id="jrn-app", round_number=1,
            type="behavioural", scheduled_at=datetime.utcnow() + timedelta(days=3),
            duration_minutes=60, status="scheduled",
        ))
        await db.commit()


async def _settle_briefs() -> None:
    while brief_service._TASKS:
        await asyncio.gather(*list(brief_service._TASKS), return_exceptions=True)


@pytest.mark.httpx_mock(should_mock=not_the_test_client)
async def test_readiness_journey_end_to_end(
    coach_database, readiness_listener, ai_off, tmp_path, monkeypatch, httpx_mock
) -> None:
    _flags(monkeypatch, True)
    await seed_pattern_sessions(coach_database)
    session_a, session_b = SUPPORTING

    async with client_for(_app()) as client:
        # Two practice sessions in one group → a pattern.
        patterns = await client.get(f"{READINESS}/patterns", params={"include_stale": "true"})
        assert patterns.status_code == 200, patterns.text
        weak = [
            pattern
            for group in patterns.json()["groups"]
            for pattern in group["patterns"]
            if pattern["kind"] == "focus" and not pattern.get("stale")
        ]
        assert weak, patterns.json()
        pattern = weak[0]

        # Pattern → focus area → plan started.
        focus = await client.post(f"{READINESS}/focus-areas", json={
            "title": "Make answers specific",
            "dimension": pattern["dimension"],
            "group": {
                "role_family": pattern["group"]["role_family"],
                "interview_type": pattern["group"]["interview_type"],
            },
            "criteria": [{"kind": "practice", "count": 1}],
        })
        assert focus.status_code == 201, focus.text
        plan = await client.post(f"{READINESS}/plans", json={"minutes": 30})
        assert plan.status_code == 201, plan.text
        started = await client.post(f"{READINESS}/plans/{plan.json()['id']}/start")
        assert started.status_code == 200, started.text
        assert started.json()["status"] == "active"

        # Round scheduled → brief "Ready" with AI off: deterministic, no model call.
        await _seed_journey_round(coach_database)
        ready = await client.get(f"{READINESS}/rounds/{JOURNEY_ROUND}/brief")
        assert ready.status_code == 200, ready.text
        assert ready.json()["state"] == "active"
        assert ready.json()["enhancement"]["state"] == "none"
        for section in ("header", "likely_questions", "stories", "watch_outs", "gaps", "ask_them"):
            assert section in ready.json(), section
        assert [story["story_id"] for story in ready.json()["stories"]] == [JOURNEY_STORY]
        await _settle_briefs()
        assert httpx_mock.get_requests() == []

        # AI on: Explain tips cite both supporting sessions; the brief is enhanced.
        configure_local_ai(tmp_path, monkeypatch)
        fake_llama(httpx_mock)
        fingerprint = await explained_fingerprint(client)
        tips = await request_tips(client, fingerprint)
        assert tips.status_code == 202, tips.text
        assert (await wait_for_operation(client, tips.json()["operation_id"]))["status"] == "succeeded"
        assert await derived_count(coach_database, kind="explain", source_id=session_a) == 1

        brief_calls: list[httpx.Request] = []
        story_text = {"value": "Delivered on time."}

        async def brief_model(request: httpx.Request) -> httpx.Response:
            brief_calls.append(request)
            return httpx.Response(200, json=chat_completion(_brief_output(story_text["value"])))

        httpx_mock.reset()
        httpx_mock.add_callback(brief_model, method="POST", url=CHAT_COMPLETIONS, is_reusable=True)
        first = await client.get(f"{READINESS}/rounds/{JOURNEY_ROUND}/brief")
        assert first.json()["enhancement"]["state"] == "enhancing"
        await _settle_briefs()
        current = await client.get(f"{READINESS}/rounds/{JOURNEY_ROUND}/brief")
        assert current.json()["enhancement"]["state"] == "current", current.json()["enhancement"]
        assert current.json()["stories"][0]["talking_point"] == "Delivered on time."
        assert len(brief_calls) == 1
        assert await derived_count(coach_database, kind="brief", source_id=JOURNEY_STORY) == 1

        # Story edited → old tips gone and hidden, never "current"; exactly one re-queue.
        async with coach_database() as db:
            await StoryRepository(db).update(JOURNEY_STORY, StoryUpdate(result="Delivered a week early"))
            await db.commit()
        assert await derived_count(coach_database, kind="brief", source_id=JOURNEY_STORY) == 0
        story_text["value"] = "Delivered a week early."
        reads = await asyncio.gather(*(
            client.get(f"{READINESS}/rounds/{JOURNEY_ROUND}/brief") for _ in range(3)
        ))
        for read in reads:
            assert read.status_code == 200, read.text
            assert read.json()["enhancement"]["state"] != "current"
            assert read.json()["stories"][0]["talking_point"] is None
        await _settle_briefs()
        assert len(brief_calls) == 2
        refreshed = await client.get(f"{READINESS}/rounds/{JOURNEY_ROUND}/brief")
        assert refreshed.json()["enhancement"]["state"] == "current"
        assert refreshed.json()["stories"][0]["talking_point"] == "Delivered a week early."

        # Round passes → brief archived, debrief due.
        async with coach_database() as db:
            await InterviewRepository(db).update(
                JOURNEY_ROUND,
                InterviewRoundUpdate(scheduled_at=datetime.utcnow() - timedelta(hours=3)),
            )
            await db.commit()
        archived = await client.get(f"{READINESS}/rounds/{JOURNEY_ROUND}/brief")
        assert archived.json()["state"] == "archived"
        due = await client.get(f"{READINESS}/rounds/{JOURNEY_ROUND}/debrief")
        assert due.status_code == 200, due.text
        assert due.json()["status"] == "due"

        # Debrief saved → QB proposal accepted once.
        added = "How do you recover a slipped delivery?"
        saved = await client.put(f"{READINESS}/rounds/{JOURNEY_ROUND}/debrief", json={
            "expected_version": 0,
            "overall": 4,
            "questions": [{"id": "jrn-q1", "text": added, "asked": True, "rating": 4}],
            "notes_text": "Synthetic rough notes about the round.",
        })
        assert saved.status_code == 200, saved.text
        assert saved.json()["status"] == "saved"
        proposal = next(
            item for item in saved.json()["proposals"] if item["kind"] == "question_bank"
        )
        accepted = await client.post(
            f"{READINESS}/rounds/{JOURNEY_ROUND}/debrief/proposals/{proposal['id']}/accept"
        )
        assert accepted.status_code == 200, accepted.text
        async with coach_database() as db:
            bank = (await db.execute(
                text("SELECT count(*) FROM question_bank_items WHERE question = :q"), {"q": added}
            )).scalar_one()
        assert bank == 1
        assert await _round_questions(coach_database, JOURNEY_ROUND) == [added]

        # Practice session hard-deleted (claim, then finalise) → its cached text is
        # gone; the debrief is kept (AC18).
        async with coach_database() as db:
            claim = await CoachPrivacyService(ConversationalSessionRepository(db)).claim_hard_deletion(
                session_a, deletion_request("p9-journey"), now=datetime.utcnow()
            )
            await db.commit()
        assert await derived_count(coach_database, source_id=session_a) == 0
        await _process_hard_deletion(claim)
        assert await derived_count(coach_database, source_id=session_a) == 0
        assert await _table_count(coach_database, "coach_interview_debriefs") == 1

        # Story soft-deleted → it leaves coverage and the brief.
        async with coach_database() as db:
            assert await StoryRepository(db).soft_delete(JOURNEY_STORY) is True
            await db.commit()
        coverage = await client.get(f"{READINESS}/coverage", params={"application_id": "jrn-app"})
        assert coverage.status_code == 200, coverage.text
        assert all(
            story["story_id"] != JOURNEY_STORY
            for item in coverage.json()["competencies"]
            for story in item["stories"]
        )
        after_delete = await client.get(f"{READINESS}/rounds/{JOURNEY_ROUND}/brief")
        assert JOURNEY_STORY not in {story["story_id"] for story in after_delete.json()["stories"]}
        assert await derived_count(coach_database, source_id=JOURNEY_STORY) == 0

        # Delete all readiness data → only Phase 1 data remains.
        await _settle_briefs()
        phase1_before = await _phase1_snapshot(coach_database)
        assert sum((await _phase2_counts(coach_database)).values()) > 0
        wiped = await client.delete(MEMORY)
        assert wiped.status_code == 200, wiped.text

    assert await _phase2_counts(coach_database) == {table: 0 for table in PHASE2_TABLES}
    assert await _phase1_snapshot(coach_database) == phase1_before
    async with coach_database() as db:
        assert await db.get(Story, JOURNEY_STORY) is not None  # soft-deleted, still Phase 1
        remaining = (await db.execute(text("SELECT id FROM interview_sessions"))).scalars().all()
    assert remaining == [session_b]
    assert await _round_questions(coach_database, JOURNEY_ROUND) == [added]
