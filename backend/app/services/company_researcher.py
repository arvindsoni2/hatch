"""Company Research Service — web scraping + Claude synthesis for interview prep."""
from __future__ import annotations

import logging

import httpx
from bs4 import BeautifulSoup

from ..prompts import render_prompt
from ..schemas.coach import CompanyResearchResponse
from .llm_client import LLMClient
from ..agents.tools.context_budgets import COMPANY_RESEARCH
from .jd_analyser import _split_jinja_output

logger = logging.getLogger(__name__)

_SEARCH_TIMEOUT = 10.0
_USER_AGENT = "Mozilla/5.0 (compatible; JobPilot-Research/1.0)"


class CompanyResearchService:
    """Researches companies via web scraping + Claude synthesis."""

    def __init__(self, claude_client: LLMClient) -> None:
        self._client = claude_client

    async def research(self, company_name: str, sector: str | None = None) -> CompanyResearchResponse:
        """Research a company by name and synthesise with Claude.

        Args:
            company_name: Company name to research.
            sector: Optional sector hint to focus the research.

        Returns:
            CompanyResearchResponse with structured company intelligence.
        """
        raw_content = await self._scrape_company_info(company_name)

        system_prompt, user_prompt = _split_jinja_output(
            render_prompt(
                "company_research.j2",
                company_name=company_name,
                sector=sector or "",
                raw_search_results=raw_content,
            )
        )
        try:
            raw = await self._client.complete_json(system_prompt, user_prompt, max_tokens=COMPANY_RESEARCH.max_output)
        except Exception as exc:
            logger.warning("Claude synthesis failed for %s: %s — using scraped content", company_name, exc)
            raw = {}

        return CompanyResearchResponse(
            company_name=company_name,
            sector=raw.get("sector", sector),
            website=raw.get("website"),
            description=raw.get("description") or f"Technology company operating in {sector or 'the technology sector'}.",
            recent_news=raw.get("recent_news", []),
            key_products=raw.get("key_products", []),
            tech_stack_signals=raw.get("tech_stack_signals", []),
        )

    async def _scrape_company_info(self, company_name: str) -> str:
        """Scrape public information about a company via DuckDuckGo HTML search.

        Args:
            company_name: Company to search for.

        Returns:
            Scraped plain text content (capped at 5000 chars).
        """
        search_query = f"{company_name} company technology careers UK"
        ddg_url = f"https://html.duckduckgo.com/html/?q={search_query.replace(' ', '+')}"

        try:
            async with httpx.AsyncClient(
                timeout=_SEARCH_TIMEOUT,
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
            ) as client:
                resp = await client.get(ddg_url)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "lxml")

                # Extract search result snippets
                results = soup.find_all("a", class_="result__snippet")
                snippets = [r.get_text(strip=True) for r in results[:10]]

                # Also try to get result titles
                titles = soup.find_all("a", class_="result__a")
                title_texts = [t.get_text(strip=True) for t in titles[:10]]

                combined = "\n".join(
                    f"Title: {t}\nSnippet: {s}"
                    for t, s in zip(title_texts, snippets)
                )
                return combined[:5000] if combined else f"No search results found for {company_name}"

        except Exception as exc:
            logger.warning("Web scrape failed for %s: %s", company_name, exc)
            return f"Company: {company_name}. Unable to retrieve live data — provide a general response."
