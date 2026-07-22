"""Company Research Service — web scraping + Claude synthesis for interview prep."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup

from ..prompts import render_prompt
from ..config import settings
from ..observability import get_telemetry, trace_stage
from ..schemas.coach import CompanyResearchResponse, ResearchSource
from .llm_client import LLMClient
from ..agents.tools.context_budgets import COMPANY_RESEARCH
from .jd_analyser import _split_jinja_output
from .coach_contracts import CoachDiagnostic, configured_model_id, run_with_stage_deadline
from .prompt_catalog import (
    prompt_contract_block,
    prompt_metadata,
    research_claim_contract,
)

logger = logging.getLogger(__name__)

_SEARCH_TIMEOUT = 10.0
_USER_AGENT = "Mozilla/5.0 (compatible; JobPilot-Research/1.0)"


@dataclass(frozen=True)
class ResearchBundle:
    """Retrieved text and the sources that produced it."""

    text: str
    sources: tuple[ResearchSource, ...]
    retrieved_at: datetime


class CompanyResearchService:
    """Researches companies via web scraping + Claude synthesis."""

    def __init__(self, claude_client: LLMClient) -> None:
        self._client = claude_client
        self.last_diagnostic: CoachDiagnostic | None = None

    @trace_stage("coach_generation", "prepare_input")
    async def research(self, company_name: str, sector: str | None = None) -> CompanyResearchResponse:
        """Research a company by name and synthesise with Claude.

        Args:
            company_name: Company name to research.
            sector: Optional sector hint to focus the research.

        Returns:
            CompanyResearchResponse with structured company intelligence.
        """
        scraped = await self._scrape_company_info(company_name)
        bundle = _as_research_bundle(scraped)

        system_prompt, user_prompt = _split_jinja_output(
            render_prompt(
                "company_research.j2",
                company_name=company_name,
                sector=sector or "",
                raw_search_results=bundle.text,
                prompt_contract=prompt_contract_block("company_research"),
                research_contract=research_claim_contract("company_research"),
            )
        )
        started = time.monotonic()
        model_call_completed = False
        try:
            raw = await run_with_stage_deadline(
                self._client.complete_json(
                    system_prompt,
                    user_prompt,
                    max_tokens=COMPANY_RESEARCH.max_output,
                ),
                settings.HATCH_COACH_TIMEOUT_COMPANY_RESEARCH_SECONDS,
            )
            get_telemetry().record_model_call(
                workflow="coach_generation",
                provider=type(self._client).__name__,
                model_id=str(getattr(self._client, "model", "configured")),
                duration_ms=(time.monotonic() - started) * 1000,
            )
            model_call_completed = True
        except Exception as exc:
            get_telemetry().record_model_call(
                workflow="coach_generation",
                provider=type(self._client).__name__,
                model_id=str(getattr(self._client, "model", "configured")),
                duration_ms=(time.monotonic() - started) * 1000,
                outcome="failed",
            )
            get_telemetry().mark_current_error(
                "company_research_failed",
                "model_error",
            )
            logger.warning("Company research synthesis failed for %s: %s", company_name, exc)
            self.last_diagnostic = self._diagnostic(
                "unavailable",
                ["coach_stage_timeout" if isinstance(exc, TimeoutError) else "coach_stage_failed"],
                started,
            )
            return _not_verified_response(company_name, sector, bundle)

        if not isinstance(raw, dict):
            if model_call_completed:
                get_telemetry().record_validation_failure(
                    "coach_generation",
                    "company_research_response_invalid",
                )
                get_telemetry().mark_current_error(
                    "company_research_response_invalid",
                    "validation_failure",
                )
            self.last_diagnostic = self._diagnostic(
                "invalid_output", ["coach_stage_failed"], started
            )
            return _not_verified_response(company_name, sector, bundle)
        source_ids = {source.source_id for source in bundle.sources}
        description = _sourced_text(raw.get("description"), source_ids)
        resolved_sector = _sourced_text(raw.get("sector"), source_ids)
        website = _sourced_text(raw.get("website"), source_ids)
        recent_news = _sourced_list(raw.get("recent_news"), source_ids)
        key_products = _sourced_list(raw.get("key_products"), source_ids)
        tech_stack_signals = _sourced_list(
            raw.get("tech_stack_signals"),
            source_ids,
        )
        supported_claims = [
            description,
            resolved_sector,
            website,
            *recent_news,
            *key_products,
            *tech_stack_signals,
        ]
        verification_state = "verified" if any(supported_claims) else "not_verified"
        self.last_diagnostic = self._diagnostic("completed", [], started)
        return CompanyResearchResponse(
            company_name=company_name,
            sector=resolved_sector or sector,
            website=website,
            description=description,
            recent_news=recent_news,
            key_products=key_products,
            tech_stack_signals=tech_stack_signals,
            sources=list(bundle.sources),
            retrieved_at=bundle.retrieved_at,
            verification_state=verification_state,
        )

    def _diagnostic(
        self, outcome: str, gates: list[str], started: float
    ) -> CoachDiagnostic:
        metadata = prompt_metadata("company_research")
        return CoachDiagnostic(
            stage="company_research",
            outcome=outcome,
            execution_mode="llm",
            prompt_id=metadata.prompt_id,
            prompt_version=metadata.prompt_version,
            output_schema_version=metadata.schema_version,
            model_id=configured_model_id(self._client),
            attempt_count=1,
            repair_count=0,
            gate_codes=gates,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    async def _scrape_company_info(self, company_name: str) -> ResearchBundle:
        """Scrape public information about a company via DuckDuckGo HTML search.

        Args:
            company_name: Company to search for.

        Returns:
            Scraped text and source provenance.
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
                retrieved_at = datetime.now(UTC)

                results = soup.find_all("a", class_="result__snippet")
                snippets = [r.get_text(strip=True) for r in results[:10]]
                titles = soup.find_all("a", class_="result__a")
                sources: list[ResearchSource] = []
                blocks: list[str] = []
                for index, (title, snippet) in enumerate(
                    zip(titles[:10], snippets),
                    start=1,
                ):
                    url = str(title.get("href") or "").strip()
                    if not url:
                        continue
                    source_id = f"source-{index}"
                    title_text = title.get_text(strip=True)
                    sources.append(
                        ResearchSource(
                            source_id=source_id,
                            title=title_text,
                            url=url,
                            retrieved_at=retrieved_at,
                        )
                    )
                    blocks.append(
                        f"[{source_id}]\nTitle: {title_text}\n"
                        f"URL: {url}\nSnippet: {snippet}"
                    )
                return ResearchBundle(
                    text="\n\n".join(blocks)[:5000],
                    sources=tuple(sources),
                    retrieved_at=retrieved_at,
                )

        except Exception as exc:
            logger.warning("Web scrape failed for %s: %s", company_name, exc)
            return ResearchBundle(
                text="",
                sources=(),
                retrieved_at=datetime.now(UTC),
            )


def _as_research_bundle(value: Any) -> ResearchBundle:
    """Preserve compatibility with callers that still provide plain text."""
    if isinstance(value, ResearchBundle):
        return value
    return ResearchBundle(
        text=value if isinstance(value, str) else "",
        sources=(),
        retrieved_at=datetime.now(UTC),
    )


def _valid_source_references(value: Any, source_ids: set[str]) -> bool:
    if not isinstance(value, dict):
        return False
    references = value.get("source_ids")
    return (
        isinstance(references, list)
        and bool(references)
        and all(reference in source_ids for reference in references)
    )


def _sourced_text(value: Any, source_ids: set[str]) -> str | None:
    if not _valid_source_references(value, source_ids):
        return None
    text = value.get("text")
    return text.strip() if isinstance(text, str) and text.strip() else None


def _sourced_list(value: Any, source_ids: set[str]) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        text
        for item in value
        if (text := _sourced_text(item, source_ids)) is not None
    ]


def _not_verified_response(
    company_name: str,
    sector: str | None,
    bundle: ResearchBundle,
) -> CompanyResearchResponse:
    return CompanyResearchResponse(
        company_name=company_name,
        sector=sector,
        sources=list(bundle.sources),
        retrieved_at=bundle.retrieved_at,
        verification_state="not_verified",
    )
