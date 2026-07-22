"""Tests for CompanyResearchService — cache hit/miss, synthesis, error fallback."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.coach import CompanyResearchResponse, ResearchSource
from app.services.company_researcher import CompanyResearchService, ResearchBundle

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

MOCK_RESEARCH_RESPONSE = {
    "sector": {"text": "Professional Services / Technology Consulting", "source_ids": ["source-1"]},
    "website": {"text": "https://www.accenture.com", "source_ids": ["source-1"]},
    "description": {
        "text": "Accenture is a global professional services company.",
        "source_ids": ["source-1"],
    },
    "recent_news": [{"text": "Accenture acquires AI startup", "source_ids": ["source-1"]}],
    "key_products": [
        {"text": "Accenture Cloud Platform", "source_ids": ["source-1"]},
        {"text": "SynOps", "source_ids": ["source-1"]},
    ],
    "tech_stack_signals": [
        {"text": "AWS, Azure, GCP", "source_ids": ["source-1"]},
        {"text": "Python, Java", "source_ids": ["source-1"]},
    ],
}

RETRIEVED_AT = datetime(2026, 7, 17, 10, 0, tzinfo=UTC)
RESEARCH_BUNDLE = ResearchBundle(
    text="[source-1] Accenture company overview and products",
    sources=(
        ResearchSource(
            source_id="source-1",
            title="Accenture",
            url="https://www.accenture.com",
            retrieved_at=RETRIEVED_AT,
        ),
    ),
    retrieved_at=RETRIEVED_AT,
)


@pytest.fixture()
def mock_claude():
    claude = MagicMock()
    claude.complete_json = AsyncMock(return_value=MOCK_RESEARCH_RESPONSE)
    return claude


@pytest.fixture()
def researcher(mock_claude) -> CompanyResearchService:
    return CompanyResearchService(mock_claude)


@pytest.fixture()
def sample_company_data():
    path = FIXTURES_DIR / "sample_company_shell.json"
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_research_returns_response_schema(researcher: CompanyResearchService) -> None:
    """research() returns a CompanyResearchResponse instance."""
    with patch.object(researcher, "_scrape_company_info", new=AsyncMock(return_value=RESEARCH_BUNDLE)):
        result = await researcher.research("Accenture", sector="Consulting")
    assert isinstance(result, CompanyResearchResponse)
    assert result.company_name == "Accenture"


@pytest.mark.asyncio
async def test_research_populates_all_fields(researcher: CompanyResearchService) -> None:
    """All CompanyResearchResponse fields are populated from Claude's response."""
    with patch.object(researcher, "_scrape_company_info", new=AsyncMock(return_value=RESEARCH_BUNDLE)):
        result = await researcher.research("Accenture")
    assert result.description
    assert isinstance(result.recent_news, list)
    assert isinstance(result.key_products, list)
    assert isinstance(result.tech_stack_signals, list)
    assert result.sources[0].url == "https://www.accenture.com"
    assert result.retrieved_at == RETRIEVED_AT
    assert result.verification_state == "verified"


@pytest.mark.asyncio
async def test_research_without_sector(researcher: CompanyResearchService) -> None:
    """research() works when sector is None."""
    with patch.object(researcher, "_scrape_company_info", new=AsyncMock(return_value=RESEARCH_BUNDLE)):
        result = await researcher.research("Accenture", sector=None)
    assert result.company_name == "Accenture"


@pytest.mark.asyncio
async def test_claude_synthesis_failure_fallback(researcher: CompanyResearchService, mock_claude) -> None:
    """If Claude synthesis fails, research returns a minimal CompanyResearchResponse."""
    mock_claude.complete_json = AsyncMock(side_effect=Exception("Claude API error"))
    with patch.object(researcher, "_scrape_company_info", new=AsyncMock(return_value=RESEARCH_BUNDLE)):
        result = await researcher.research("Accenture")
    assert isinstance(result, CompanyResearchResponse)
    assert result.company_name == "Accenture"


@pytest.mark.asyncio
async def test_company_research_timeout_is_explicit(
    researcher: CompanyResearchService, mock_claude
) -> None:
    mock_claude.complete_json.side_effect = TimeoutError

    result = await researcher.research("Accenture", "Consulting")

    assert result.verification_state == "not_verified"
    assert researcher.last_diagnostic is not None
    assert researcher.last_diagnostic.outcome == "unavailable"
    assert researcher.last_diagnostic.gate_codes == ["coach_stage_timeout"]
    mock_claude.complete_json.assert_awaited_once()
    assert result.verification_state == "not_verified"
    assert result.description is None
    assert result.recent_news == []
    assert result.key_products == []
    assert result.tech_stack_signals == []


@pytest.mark.asyncio
async def test_unknown_source_references_are_dropped(
    researcher: CompanyResearchService,
    mock_claude,
) -> None:
    mock_claude.complete_json = AsyncMock(
        return_value={
            "description": {"text": "Invented claim", "source_ids": ["source-404"]},
            "recent_news": [{"text": "Invented news", "source_ids": ["source-404"]}],
        }
    )
    with patch.object(researcher, "_scrape_company_info", new=AsyncMock(return_value=RESEARCH_BUNDLE)):
        result = await researcher.research("Accenture")

    assert result.description is None
    assert result.recent_news == []
    assert result.verification_state == "not_verified"


@pytest.mark.asyncio
async def test_prompt_requires_source_ids_and_metadata(
    researcher: CompanyResearchService,
    mock_claude,
) -> None:
    with patch.object(researcher, "_scrape_company_info", new=AsyncMock(return_value=RESEARCH_BUNDLE)):
        await researcher.research("Accenture")

    system_prompt, user_prompt = mock_claude.complete_json.await_args.args[:2]
    combined = system_prompt + user_prompt
    assert '"prompt_id": "company_research"' in combined
    assert "source_ids" in combined
    assert "retrieval timestamp" in combined.lower()


@pytest.mark.asyncio
async def test_fixture_data_structure(sample_company_data: dict) -> None:
    """Fixture JSON matches CompanyResearchResponse schema."""
    response = CompanyResearchResponse(**sample_company_data)
    assert response.company_name == "Accenture"
    assert len(response.recent_news) > 0
    assert len(response.tech_stack_signals) > 0
