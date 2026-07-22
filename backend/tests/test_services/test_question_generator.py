"""Tests for QuestionGeneratorService — question count, category weights, model answers."""
from __future__ import annotations

import copy
import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.coach import QuestionPresentation, SessionConfig
from app.services.question_generator import (
    QuestionGenerationContractError,
    QuestionGenerationResult,
    QuestionGeneratorService,
    _CATEGORY_WEIGHTS,
    _build_requirements,
    _validate_questions,
)

MOCK_QUESTIONS_RESPONSE = [
    {
        "text": "How would you design a cloud architecture for a large enterprise?",
        "category": "Technical",
        "difficulty": "hard",
        "context": "Focus on AWS or Azure solutions architecture.",
    },
    {
        "text": "How would you manage conflicting stakeholder priorities?",
        "category": "Behavioural",
        "difficulty": "medium",
        "context": None,
    },
    {
        "text": "How would you approach migrating a monolith to microservices in 6 months?",
        "category": "Situational",
        "difficulty": "hard",
        "context": "Assume a 200-service estate.",
    },
    {
        "text": "What domain knowledge do you bring to financial services cloud projects?",
        "category": "Domain",
        "difficulty": "medium",
        "context": None,
    },
    {
        "text": "What does being commercially aware mean to you as an architect?",
        "category": "Commercial",
        "difficulty": "medium",
        "context": None,
    },
]


@pytest.fixture()
def mock_claude():
    claude = MagicMock()

    async def response_with_allowed_ids(_system: str, user: str, **_kwargs):
        requirement_ids = list(dict.fromkeys(re.findall(r"requirement-[a-f0-9]{12}", user)))
        payload = copy.deepcopy(MOCK_QUESTIONS_RESPONSE)
        for index, question in enumerate(payload):
            question["requirement_id"] = requirement_ids[index % len(requirement_ids)]
        return payload

    claude.complete_json = AsyncMock(side_effect=response_with_allowed_ids)
    return claude


@pytest.fixture()
def generator(mock_claude) -> QuestionGeneratorService:
    return QuestionGeneratorService(mock_claude)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_returns_question_presentations(generator: QuestionGeneratorService) -> None:
    """generate() returns a list of QuestionPresentation objects."""
    config = SessionConfig(question_count=5)
    result = await generator.generate(
        config=config,
        company_name="Accenture",
        role_title="Solutions Architect",
    )
    assert isinstance(result, QuestionGenerationResult)
    assert all(isinstance(q, QuestionPresentation) for q in result)


@pytest.mark.asyncio
async def test_generate_correct_count(generator: QuestionGeneratorService) -> None:
    """generate() returns exactly the number of questions requested."""
    config = SessionConfig(question_count=5)
    result = await generator.generate(config=config, company_name="Accenture", role_title="SA")
    assert len(result) == 5


@pytest.mark.asyncio
async def test_question_has_required_fields(generator: QuestionGeneratorService) -> None:
    """Each QuestionPresentation has id, text, category, difficulty, num, total."""
    config = SessionConfig(question_count=5)
    result = await generator.generate(config=config, company_name="Accenture", role_title="SA")
    for q in result:
        assert q.id
        assert q.text
        assert q.category in {"Technical", "Behavioural", "Situational", "Domain", "Culture", "Commercial"}
        assert q.difficulty in {"easy", "medium", "hard"}
        assert q.num >= 1
        assert q.total == 5


@pytest.mark.asyncio
async def test_category_weights_defined() -> None:
    """_CATEGORY_WEIGHTS sums to approximately 1.0."""
    total = sum(_CATEGORY_WEIGHTS.values())
    assert abs(total - 1.0) < 0.01


def test_question_rejects_confirmed_second_person_history() -> None:
    result = _validate_questions(
        [{
            "text": "Tell me how you led the Acme migration.",
            "category": "Behavioural",
            "difficulty": "medium",
            "requirement_id": "requirement-1",
        }],
        expected_count=1,
        requirement_ids=("requirement-1",),
    )

    assert result.accepted == []
    assert "coach_question_candidate_claim" in result.gate_codes


def test_question_rejects_unseen_named_candidate_action() -> None:
    result = _validate_questions(
        [{
            "text": "Tell me how Alex spearheaded the Acme migration.",
            "category": "Behavioural",
            "difficulty": "medium",
            "requirement_id": "requirement-1",
        }],
        expected_count=1,
        requirement_ids=("requirement-1",),
    )

    assert result.accepted == []
    assert "coach_question_candidate_claim" in result.gate_codes


@pytest.mark.asyncio
async def test_generate_with_company_research(generator: QuestionGeneratorService) -> None:
    """generate() succeeds when company_research is provided."""
    from app.schemas.coach import CompanyResearchResponse
    config = SessionConfig(question_count=5)
    research = CompanyResearchResponse(
        company_name="Accenture",
        sector="Consulting",
        website=None,
        description="Global consulting firm.",
        recent_news=[],
        key_products=[],
        tech_stack_signals=[],
    )
    result = await generator.generate(
        config=config,
        company_name="Accenture",
        role_title="SA",
        company_research=research,
    )
    assert len(result) == 5


@pytest.mark.asyncio
async def test_generate_with_jd_text(generator: QuestionGeneratorService) -> None:
    """generate() accepts jd_text for richer question generation."""
    config = SessionConfig(question_count=5)
    result = await generator.generate(
        config=config,
        company_name="Accenture",
        role_title="SA",
        jd_text="Senior Solutions Architect, AWS, Terraform, £700/day, Outside IR35.",
    )
    assert len(result) == 5
    assert all(question.requirement_id for question in result)


@pytest.mark.asyncio
async def test_questions_are_mapped_deduplicated_and_versioned(mock_claude) -> None:
    requirement_ids = [
        item["requirement_id"]
        for item in _build_requirements(
            "Design secure AWS platforms.\nLead architecture reviews."
        )
    ]
    mock_claude.complete_json = AsyncMock(
        side_effect=[
            {
            "questions": [
                {
                    "text": "How do you design secure AWS platforms?",
                    "category": "Technical",
                    "difficulty": "hard",
                    "requirement_id": requirement_ids[0],
                },
                {
                    "text": " How do you design secure AWS platforms? ",
                    "category": "General",
                    "difficulty": "hard",
                    "requirement_id": "unknown",
                },
            ]
            },
            {
                "questions": [
                    {
                        "text": "How do you lead architecture reviews?",
                        "category": "Behavioural",
                        "difficulty": "medium",
                        "requirement_id": requirement_ids[1],
                    }
                ]
            },
        ]
    )
    generator = QuestionGeneratorService(mock_claude)
    result = await generator.generate(
        config=SessionConfig(question_count=2),
        company_name="Example",
        role_title="Cloud Architect",
        jd_text="Design secure AWS platforms.\nLead architecture reviews.",
    )

    assert len(result) == 2
    assert [question.requirement_id for question in result] == requirement_ids
    assert result[0].category == "Technical"
    assert result.initial_diagnostic.gate_codes == [
        "coach_question_duplicate",
        "coach_question_category_invalid",
        "coach_question_requirement_unknown",
        "coach_question_count_mismatch",
    ]
    assert result.repair_diagnostic is not None
    assert result.final_diagnostic.outcome == "completed"
    assert result.final_diagnostic.repair_count == 1
    system_prompt, user_prompt = mock_claude.complete_json.await_args_list[0].args[:2]
    combined = system_prompt + user_prompt
    assert '"prompt_id": "question_generation"' in combined
    assert "Do not imply that the candidate has experience" in combined


@pytest.mark.asyncio
async def test_question_generation_performs_at_most_one_repair() -> None:
    requirement_id = _build_requirements("Cloud architecture")[0]["requirement_id"]
    invalid = {
        "questions": [
            {
                "text": "How would you design it?",
                "category": "Technical",
                "difficulty": "medium",
                "requirement_id": "unknown",
            }
        ]
    }
    client = MagicMock()
    client.complete_json = AsyncMock(side_effect=[invalid, invalid])

    with pytest.raises(QuestionGenerationContractError) as caught:
        await QuestionGeneratorService(client).generate(
            config=SessionConfig(question_count=1),
            company_name="Example",
            role_title="Architect",
            jd_text="Cloud architecture",
        )

    assert client.complete_json.await_count == 2
    assert caught.value.result.questions == []
    assert caught.value.result.final_diagnostic.outcome == "invalid_output"
    assert "coach_question_repair_exhausted" in (
        caught.value.result.final_diagnostic.gate_codes
    )
    assert requirement_id not in [
        question.requirement_id for question in caught.value.result.questions
    ]


@pytest.mark.asyncio
async def test_question_generation_cannot_activate_partial_repaired_set() -> None:
    requirement_id = _build_requirements("Cloud architecture")[0]["requirement_id"]
    one_valid = {
        "questions": [
            {
                "text": "How would you design a cloud platform?",
                "category": "Technical",
                "difficulty": "medium",
                "requirement_id": requirement_id,
            }
        ]
    }
    client = MagicMock()
    client.complete_json = AsyncMock(side_effect=[one_valid, {"questions": []}])

    with pytest.raises(QuestionGenerationContractError) as caught:
        await QuestionGeneratorService(client).generate(
            config=SessionConfig(question_count=2),
            company_name="Example",
            role_title="Architect",
            jd_text="Cloud architecture",
        )

    assert caught.value.result.questions == []
    assert client.complete_json.await_count == 2


@pytest.mark.asyncio
async def test_question_generation_timeout_does_not_run_repair(monkeypatch) -> None:
    client = MagicMock()
    client.complete_json = AsyncMock(side_effect=TimeoutError)
    monkeypatch.setattr(
        "app.services.question_generator.settings.HATCH_COACH_TIMEOUT_QUESTION_GENERATION_SECONDS",
        10,
    )

    with pytest.raises(QuestionGenerationContractError) as caught:
        await QuestionGeneratorService(client).generate(
            config=SessionConfig(question_count=1),
            company_name="Example",
            role_title="Architect",
        )

    assert client.complete_json.await_count == 1
    assert caught.value.result.final_diagnostic.outcome == "unavailable"
    assert caught.value.result.final_diagnostic.gate_codes == ["coach_stage_timeout"]
