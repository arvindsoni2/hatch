"""Tests for TechnicalDrillsService — Phase C."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.coach_session import SessionQuestion
from app.schemas.coach import TechnicalDrill
from app.services.technical_drills import TechnicalDrillsService


def _make_question(
    id_: str = "q-001",
    text: str = "Design a URL shortener",
    category: str = "Technical",
) -> SessionQuestion:
    q = MagicMock(spec=SessionQuestion)
    q.id = id_
    q.text = text
    q.category = category
    return q


# ---------------------------------------------------------------------------
# test_build_drills_filters_technical_only
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_drills_filters_technical_only() -> None:
    """Only Technical and Domain questions should receive drills."""
    mock_claude = MagicMock()
    mock_claude.complete = AsyncMock(
        return_value=json.dumps({
            "walkthrough": "Step 1: Hash the URL. Step 2: Store in Redis. Step 3: Return short code.",
            "drill_prompt": "Explain out loud how you would design this system from scratch.",
        })
    )

    svc = TechnicalDrillsService(mock_claude)

    questions = [
        _make_question("q-1", "Tell me about a time you led a team", "Behavioural"),
        _make_question("q-2", "Design a distributed cache", "Technical"),
        _make_question("q-3", "What is your salary expectation?", "Culture"),
        _make_question("q-4", "Explain REST vs GraphQL", "Domain"),
    ]

    drills = await svc.build_drills(questions)

    # Only Technical and Domain questions get drills
    assert len(drills) == 2
    drill_question_ids = {d.question_id for d in drills}
    assert "q-2" in drill_question_ids
    assert "q-4" in drill_question_ids
    assert "q-1" not in drill_question_ids
    assert "q-3" not in drill_question_ids

    # Validate drill content
    for drill in drills:
        assert isinstance(drill, TechnicalDrill)
        assert drill.walkthrough
        assert drill.drill_prompt


@pytest.mark.asyncio
async def test_build_drills_case_insensitive_category() -> None:
    """Category matching should be case-insensitive (e.g., 'technical', 'DOMAIN')."""
    mock_claude = MagicMock()
    mock_claude.complete = AsyncMock(
        return_value=json.dumps({
            "walkthrough": "Worked example here.",
            "drill_prompt": "Explain out loud.",
        })
    )
    svc = TechnicalDrillsService(mock_claude)

    questions = [
        _make_question("q-a", "Describe microservices", "technical"),
        _make_question("q-b", "Explain CQRS", "DOMAIN"),
        _make_question("q-c", "Tell me about yourself", "Behavioural"),
    ]

    drills = await svc.build_drills(questions)
    assert len(drills) == 2
    assert {d.question_id for d in drills} == {"q-a", "q-b"}


@pytest.mark.asyncio
async def test_build_drills_empty_when_no_technical() -> None:
    """Returns empty list when there are no technical or domain questions."""
    mock_claude = MagicMock()
    mock_claude.complete = AsyncMock()

    svc = TechnicalDrillsService(mock_claude)
    questions = [
        _make_question("q-1", "Tell me about yourself", "Behavioural"),
        _make_question("q-2", "What motivates you?", "Culture"),
    ]
    drills = await svc.build_drills(questions)
    assert drills == []
    mock_claude.complete.assert_not_called()


# ---------------------------------------------------------------------------
# test_build_drills_graceful_on_llm_failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_drills_graceful_on_llm_failure() -> None:
    """When the LLM raises an exception, returns empty list (graceful degradation)."""
    mock_claude = MagicMock()
    mock_claude.complete = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

    svc = TechnicalDrillsService(mock_claude)
    questions = [
        _make_question("q-1", "How would you design a distributed system?", "Technical"),
    ]

    drills = await svc.build_drills(questions)
    assert drills == []


@pytest.mark.asyncio
async def test_build_drills_skips_invalid_json() -> None:
    """Questions where LLM returns invalid JSON are silently skipped."""
    mock_claude = MagicMock()
    mock_claude.complete = AsyncMock(return_value="not valid json at all")

    svc = TechnicalDrillsService(mock_claude)
    questions = [
        _make_question("q-1", "Explain the CAP theorem", "Technical"),
    ]

    drills = await svc.build_drills(questions)
    assert drills == []


@pytest.mark.asyncio
async def test_build_drills_partial_failure() -> None:
    """If one question fails and another succeeds, only the successful one is returned."""
    call_count = 0

    async def side_effect(*args, **kwargs) -> str:  # noqa: ANN002
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("LLM failure on first call")
        return json.dumps({
            "walkthrough": "Worked example.",
            "drill_prompt": "Explain out loud.",
        })

    mock_claude = MagicMock()
    mock_claude.complete = AsyncMock(side_effect=side_effect)

    svc = TechnicalDrillsService(mock_claude)
    questions = [
        _make_question("q-fail", "Explain ACID properties", "Technical"),
        _make_question("q-ok", "How does a B-tree index work?", "Domain"),
    ]

    drills = await svc.build_drills(questions)
    assert len(drills) == 1
    assert drills[0].question_id == "q-ok"
