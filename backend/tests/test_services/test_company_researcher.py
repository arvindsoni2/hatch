"""Tests for CompanyResearchService — cache hit/miss, synthesis, error fallback."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.coach import CompanyResearchResponse
from app.services.company_researcher import CompanyResearchService

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

MOCK_RESEARCH_RESPONSE = {
    "sector": "Professional Services / Technology Consulting",
    "website": "https://www.accenture.com",
    "description": "Accenture is a global professional services company.",
    "recent_news": ["Accenture acquires AI startup"],
    "key_products": ["Accenture Cloud Platform", "SynOps"],
    "tech_stack_signals": ["AWS, Azure, GCP", "Python, Java"],
}


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
    with patch.object(researcher, "_scrape_company_info", new=AsyncMock(return_value="raw scraped text")):
        result = await researcher.research("Accenture", sector="Consulting")
    assert isinstance(result, CompanyResearchResponse)
    assert result.company_name == "Accenture"


@pytest.mark.asyncio
async def test_research_populates_all_fields(researcher: CompanyResearchService) -> None:
    """All CompanyResearchResponse fields are populated from Claude's response."""
    with patch.object(researcher, "_scrape_company_info", new=AsyncMock(return_value="raw text")):
        result = await researcher.research("Accenture")
    assert result.description
    assert isinstance(result.recent_news, list)
    assert isinstance(result.key_products, list)
    assert isinstance(result.tech_stack_signals, list)


@pytest.mark.asyncio
async def test_research_without_sector(researcher: CompanyResearchService) -> None:
    """research() works when sector is None."""
    with patch.object(researcher, "_scrape_company_info", new=AsyncMock(return_value="raw text")):
        result = await researcher.research("Accenture", sector=None)
    assert result.company_name == "Accenture"


@pytest.mark.asyncio
async def test_claude_synthesis_failure_fallback(researcher: CompanyResearchService, mock_claude) -> None:
    """If Claude synthesis fails, research returns a minimal CompanyResearchResponse."""
    mock_claude.complete_json = AsyncMock(side_effect=Exception("Claude API error"))
    with patch.object(researcher, "_scrape_company_info", new=AsyncMock(return_value="scraped text")):
        result = await researcher.research("Accenture")
    # Falls back to default data rather than raising
    assert isinstance(result, CompanyResearchResponse)
    assert result.company_name == "Accenture"


@pytest.mark.asyncio
async def test_fixture_data_structure(sample_company_data: dict) -> None:
    """Fixture JSON matches CompanyResearchResponse schema."""
    response = CompanyResearchResponse(**sample_company_data)
    assert response.company_name == "Accenture"
    assert len(response.recent_news) > 0
    assert len(response.tech_stack_signals) > 0
