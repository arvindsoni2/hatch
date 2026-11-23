"""S2 proposals, Tier T note extraction and competency extraction (P8).

Extraction passes ids and reads content at call time (spec §10); accepting a
proposal writes through the Question Bank and Story public services only.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.application import Application, InterviewRound
from app.models.coach_readiness import CoachDerivedText, CoachInterviewDebrief
from app.models.job import JobPosting
from app.models.question_bank import QuestionBankItem
from app.models.story import Story, StoryUsage
from app.services.coach_readiness import coverage as coverage_module
from app.services.coach_readiness import debrief as debrief_module
from app.services.coach_readiness.contracts import DebriefQuestion, SaveDebriefCommand
from app.services.coach_readiness.debrief import DebriefService
from app.services.coach_readiness.tiers import TierConfig
from app.services.story_service import StoryService

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
CHAT_COMPLETIONS = re.compile(r".*/chat/completions$")

_TIER = TierConfig(
    tier="T", route="llm-triage", model_id="synthetic-t", thinking=False,
    max_input_tokens=1_200, max_output_tokens=512, deadline_s=60,
)


@pytest.fixture(autouse=True)
def _enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "HATCH_COACH_DEBRIEF_ENABLED", True)
    monkeypatch.setattr(settings, "HATCH_COACH_STORY_COVERAGE_ENABLED", True)
    monkeypatch.setattr(debrief_module, "load_runtime", lambda: {"ai_mode": "local"})
    monkeypatch.setattr(coverage_module, "load_runtime", lambda: {"ai_mode": "local"})
    monkeypatch.setattr(debrief_module, "load_tier_map", lambda: {"T": _TIER})
    monkeypatch.setattr(coverage_module, "load_tier_map", lambda: {"T": _TIER})


def _chat(content: str) -> dict:
    return {
        "id": "chatcmpl-synthetic",
        "object": "chat.completion",
        "created": 0,
        "model": "synthetic-t",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80},
    }


async def _seed(db: AsyncSession, *, description: str | None = None) -> None:
    db.add(JobPosting(
        id="prop-job", title="Delivery Lead", company="Northwind",
        url="https://example.test/prop", source="synthetic",
        description=description or "We are hiring a delivery lead.\n- Own quarterly planning across four teams.",
    ))
    # Flush in FK order: the file-backed race DB enforces foreign keys.
    await db.flush()
    db.add(Application(id="prop-app", job_id="prop-job", status="interview", priority="normal"))
    db.add(InterviewRound(
        id="prop-round", application_id="prop-app", round_number=1,
        type="behavioural", scheduled_at=datetime(2026, 11, 9, 10, 0),
        status="scheduled",
    ))
    db.add(QuestionBankItem(
        id="prop-qb-existing", type="interview_question",
        title="Existing question", question="Tell me about a delivery you rescued.",
        answer_draft="Draft",
    ))
    db.add(Story(
        id="prop-story", title="Rescued a late delivery", slug="prop-story",
        situation="Synthetic situation", task="Synthetic task", action="Synthetic action",
        result="Delivered on time", tags=["delivery"], skills=["delivery"],
    ))
    await db.commit()


def _question(
    text: str,
    *,
    asked: bool = True,
    source_ref: dict | None = None,
    story_id: str | None = None,
    rating: int | None = None,
) -> DebriefQuestion:
    return DebriefQuestion(
        id=f"q-{abs(hash(text)) % 10_000}", text=text, source_ref=source_ref,
        asked=asked, rating=rating, story_id=story_id,
    )


@pytest.mark.asyncio
async def test_only_unsourced_new_questions_proposed(db_session: AsyncSession) -> None:
    await _seed(db_session)
    command = SaveDebriefCommand(
        expected_version=0,
        overall=4,
        questions=(
            # Ticked from the likely-question list: already in the Question Bank.
            _question(
                "Tell me about a delivery you rescued.",
                source_ref={"kind": "question_bank_item", "id": "prop-qb-existing"},
            ),
            # Same normalised text as an existing item: a duplicate.
            _question("Tell me about a  delivery you rescued."),
            # Not asked: never proposed.
            _question("How do you plan a quarter?", asked=False),
            # New, unsourced and asked: proposed exactly once.
            _question("How do you handle a stakeholder who disagrees?"),
        ),
    )

    result = await DebriefService(db_session).save("prop-round", command, NOW)

    qb = [item for item in result.proposals if item.kind == "question_bank"]
    assert len(qb) == 1
    assert qb[0].questions == ("How do you handle a stakeholder who disagrees?",)
    stories = [item for item in result.proposals if item.kind == "story_use"]
    assert stories == []


@pytest.mark.asyncio
async def test_qb_proposal_accept_is_idempotent(db_session: AsyncSession) -> None:
    await _seed(db_session)
    service = DebriefService(db_session)
    saved = await service.save(
        "prop-round",
        SaveDebriefCommand(
            expected_version=0,
            overall=4,
            questions=(_question("How do you handle a stakeholder who disagrees?"),),
        ),
        NOW,
    )
    proposal = next(item for item in saved.proposals if item.kind == "question_bank")

    first = await service.accept_proposal("prop-round", proposal.id, NOW)
    second = await service.accept_proposal("prop-round", proposal.id, NOW)

    items = (
        await db_session.execute(
            select(QuestionBankItem).where(
                QuestionBankItem.question
                == "How do you handle a stakeholder who disagrees?"
            )
        )
    ).scalars().all()
    assert len(items) == 1
    assert items[0].linked_applications == ["prop-app"]
    assert items[0].source == "interview_prep"
    assert first.proposals[-1].accepted is True
    assert second.proposals[-1].accepted is True


@pytest.mark.asyncio
async def test_story_use_recorded_through_public_route(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(db_session)
    recorded: list[str] = []
    original = StoryService.record_use

    async def spy(self, story_id: str, db: AsyncSession) -> bool:
        recorded.append(story_id)
        return await original(self, story_id, db)

    monkeypatch.setattr(StoryService, "record_use", spy)

    service = DebriefService(db_session)
    saved = await service.save(
        "prop-round",
        SaveDebriefCommand(
            expected_version=0,
            overall=4,
            questions=(
                _question(
                    "How do you handle a stakeholder who disagrees?",
                    story_id="prop-story",
                ),
            ),
        ),
        NOW,
    )
    proposal = next(item for item in saved.proposals if item.kind == "story_use")

    await service.accept_proposal("prop-round", proposal.id, NOW)

    assert recorded == ["prop-story"]
    usages = (
        await db_session.execute(
            select(StoryUsage).where(StoryUsage.story_id == "prop-story")
        )
    ).scalars().all()
    assert len(usages) == 1


@pytest.mark.asyncio
async def test_notes_saved_before_extraction_and_passed_by_id(
    db_session: AsyncSession, httpx_mock
) -> None:
    canary = "CANARY-notes-7031"
    await _seed(db_session)
    service = DebriefService(db_session)
    # The notes are saved in a notes-only draft first (spec §7.6).
    draft = await service.save(
        "prop-round",
        SaveDebriefCommand(
            expected_version=0,
            overall=None,
            notes_text=f"Asked about budgets. {canary}",
        ),
        NOW,
    )
    assert draft.status == "draft"

    requests: list[httpx.Request] = []

    async def completion(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_chat(
            json.dumps({"questions": ["How did you manage the budget?"]})
        ))

    httpx_mock.add_callback(
        completion, method="POST", url=CHAT_COMPLETIONS, is_reusable=True
    )

    questions = await service.extract_notes("prop-round", NOW)

    assert questions == ("How did you manage the budget?",)
    assert len(requests) == 1
    # The model saw the notes; no persisted record ever contains them.
    assert canary in requests[0].read().decode("utf-8")
    derived = (
        await db_session.execute(select(CoachDerivedText))
    ).scalars().all()
    assert all(canary not in json.dumps(row.text_json) for row in derived)


@pytest.mark.asyncio
async def test_extract_is_a_proposal_until_confirmed(
    db_session: AsyncSession, httpx_mock
) -> None:
    await _seed(db_session)
    service = DebriefService(db_session)
    await service.save(
        "prop-round",
        SaveDebriefCommand(
            expected_version=0,
            overall=None,
            notes_text="Asked about budgets and stakeholder sign-off.",
        ),
        NOW,
    )
    httpx_mock.add_callback(
        lambda request: httpx.Response(200, json=_chat(json.dumps({
            "questions": ["How did you manage the budget?", "How did you handle sign-off?"] * 6
        }))),
        method="POST", url=CHAT_COMPLETIONS, is_reusable=True,
    )

    questions = await service.extract_notes("prop-round", NOW)

    assert len(questions) == 12
    assert all(len(text) <= 120 for text in questions)
    row = (
        await db_session.execute(
            select(CoachInterviewDebrief).where(
                CoachInterviewDebrief.interview_round_id == "prop-round"
            )
        )
    ).scalar_one()
    # Nothing was saved: extraction is a proposal the candidate confirms.
    assert row.questions_json == []
    assert row.status == "draft"


@pytest.mark.asyncio
async def test_competency_extract_input_is_requirement_lines_within_budget(
    db_session: AsyncSession, httpx_mock
) -> None:
    description = (
        "We are a friendly company with a long history and a lovely office.\n"
        "About us: we value culture, coffee and conversation.\n"
        + "\n".join(
            f"- Own quarterly planning across team {index} and keep dependencies visible."
            for index in range(120)
        )
    )
    await _seed(db_session, description=description)
    requests: list[httpx.Request] = []

    async def completion(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_chat(
            json.dumps({"competencies": ["quarterly planning", "dependency management"]})
        ))

    httpx_mock.add_callback(
        completion, method="POST", url=CHAT_COMPLETIONS, is_reusable=True
    )

    result = await coverage_module.coverage_for_application(db_session, "prop-app")

    assert len(requests) == 1
    sent = json.loads(requests[0].read())["messages"][1]["content"]
    assert "friendly company" not in sent
    assert sent.startswith("- Own quarterly planning")
    assert len(sent) <= 4_500  # ≤ 1,200 tokens at 4 characters per token (AC34).
    assert any(
        item.label == "from the job description" for item in result.competencies
    )


@pytest.mark.asyncio
async def test_extracted_competencies_labelled_and_capped(
    db_session: AsyncSession, httpx_mock
) -> None:
    await _seed(db_session)
    httpx_mock.add_callback(
        lambda request: httpx.Response(200, json=_chat(json.dumps({
            # The output contract caps at four; duplicates are dropped here too.
            "competencies": [
                "quarterly planning", "quarterly  planning", "risk management",
                "stakeholder reporting",
            ]
        }))),
        method="POST", url=CHAT_COMPLETIONS, is_reusable=True,
    )

    result = await coverage_module.coverage_for_application(db_session, "prop-app")

    extracted = [item for item in result.competencies if item.label]
    assert [item.competency for item in extracted] == [
        "quarterly planning", "risk management", "stakeholder reporting",
    ]
    assert all(item.label == "from the job description" for item in extracted)


def _committing_app(factory):
    from fastapi import FastAPI

    from app.database import Base, get_db  # noqa: F401  (Base imported above)
    from app.routers.coach_readiness import router

    app = FastAPI()
    app.include_router(router)

    async def request_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = request_db
    return app


async def _accept_race(tmp_path, *, story_id: str | None):
    from fastapi import FastAPI  # noqa: F401

    from app.database import Base as _Base, create_sqlite_engine
    from sqlalchemy.ext.asyncio import async_sessionmaker
    import asyncio

    engine = create_sqlite_engine(f"sqlite+aiosqlite:///{tmp_path / 'accept.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(_Base.metadata.create_all)
    try:
        async with factory() as db:
            await _seed(db)
            saved = await DebriefService(db).save(
                "prop-round",
                SaveDebriefCommand(
                    expected_version=0,
                    overall=4,
                    questions=(
                        _question(
                            "How do you handle a stakeholder who disagrees?",
                            story_id=story_id,
                        ),
                    ),
                ),
                NOW,
            )
            await db.commit()
            proposal = next(
                item for item in saved.proposals
                if item.kind == ("story_use" if story_id else "question_bank")
            )
        app = _committing_app(factory)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            responses = await asyncio.gather(*(
                client.post(
                    "/api/coach/readiness/rounds/prop-round/debrief/proposals/"
                    f"{proposal.id}/accept"
                )
                for _ in range(3)
            ))
        for response in responses:
            assert response.status_code == 200, response.text
        return factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_accepts_make_one_question_bank_item(tmp_path) -> None:
    factory = await _accept_race(tmp_path, story_id=None)

    async with factory() as db:
        items = (
            await db.execute(
                select(QuestionBankItem).where(
                    QuestionBankItem.question
                    == "How do you handle a stakeholder who disagrees?"
                )
            )
        ).scalars().all()
    assert len(items) == 1


@pytest.mark.asyncio
async def test_concurrent_accepts_record_one_story_use(tmp_path) -> None:
    factory = await _accept_race(tmp_path, story_id="prop-story")

    async with factory() as db:
        usages = (
            await db.execute(
                select(StoryUsage).where(StoryUsage.story_id == "prop-story")
            )
        ).scalars().all()
    assert len(usages) == 1


@pytest.mark.asyncio
async def test_notes_only_save_keeps_a_saved_debrief(db_session: AsyncSession) -> None:
    await _seed(db_session)
    service = DebriefService(db_session)
    question = _question("How do you handle a stakeholder who disagrees?")
    saved = await service.save(
        "prop-round",
        SaveDebriefCommand(
            expected_version=0,
            overall=4,
            expectation="yes",
            questions=(question,),
            went_well="It went well.",
            do_differently="Prepare budgets.",
        ),
        NOW,
    )
    assert saved.status == "saved"

    with_notes = await service.save(
        "prop-round",
        SaveDebriefCommand(
            expected_version=saved.version,
            overall=None,
            notes_text="Asked about budgets and sign-off.",
        ),
        NOW,
    )

    assert with_notes.status == "saved"
    assert with_notes.version == saved.version + 1
    assert with_notes.overall == 4
    assert with_notes.expectation == "yes"
    assert [item.text for item in with_notes.questions] == [question.text]
    assert with_notes.went_well == "It went well."
    assert with_notes.do_differently == "Prepare budgets."
    assert with_notes.notes_text == "Asked about budgets and sign-off."


@pytest.mark.asyncio
async def test_notes_only_save_moves_a_skipped_debrief_back_to_draft(
    db_session: AsyncSession,
) -> None:
    await _seed(db_session)
    service = DebriefService(db_session)
    skipped = await service.skip("prop-round", 0, NOW)
    assert skipped.status == "skipped"

    draft = await service.save(
        "prop-round",
        SaveDebriefCommand(
            expected_version=skipped.version,
            overall=None,
            notes_text="Asked about budgets.",
        ),
        NOW,
    )

    assert draft.status == "draft"
    assert draft.overall is None
