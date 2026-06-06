"""Tests for QuestionGeneratorService — question count, category weights, model answers."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.coach import QuestionPresentation, SessionConfig
from app.services.question_generator import QuestionGeneratorService, _CATEGORY_WEIGHTS

MOCK_QUESTIONS_RESPONSE = [
    {
        "text": "Tell me about a time you designed a cloud architecture for a large enterprise.",
        "category": "Technical",
        "difficulty": "hard",
        "context": "Focus on AWS or Azure solutions architecture.",
        "model_answer": "STAR: Situation — FTSE 100 retailer...",
    },
    {
        "text": "Describe a situation where you had to manage conflicting stakeholder priorities.",
        "category": "Behavioural",
        "difficulty": "medium",
        "context": None,
        "model_answer": "STAR: Situation — Board-level disagreement...",
    },
    {
        "text": "How would you approach migrating a monolith to microservices in 6 months?",
        "category": "Situational",
        "difficulty": "hard",
        "context": "Assume a 200-service estate.",
        "model_answer": "I would start with domain decomposition...",
    },
    {
        "text": "What domain knowledge do you bring to financial services cloud projects?",
        "category": "Domain",
        "difficulty": "medium",
        "context": None,
        "model_answer": "Having delivered three FS cloud migrations...",
    },
    {
        "text": "What does being commercially aware mean to you as an architect?",
        "category": "Commercial",
        "difficulty": "medium",
        "context": None,
        "model_answer": "Commercial awareness means understanding TCO...",
    },
]


@pytest.fixture()
def mock_claude():
    claude = MagicMock()
    claude.complete_json = AsyncMock(return_value=MOCK_QUESTIONS_RESPONSE)
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
    assert isinstance(result, list)
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
