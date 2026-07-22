"""JD Analyser — parses job descriptions and computes skill match against the master CV."""
from __future__ import annotations

import ipaddress
import logging
import socket
import time
from copy import deepcopy
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.tools.context_budgets import JD_ANALYSIS
from ..prompts import render_prompt
from ..observability import get_telemetry
from ..schemas.tailor import ATSKeywords, JDAnalysisResult, SkillMatchResult
from .llm_client import LLMClient
from .prompt_catalog import prompt_contract_block, source_contains

logger = logging.getLogger(__name__)

# Tag taxonomy from master_cv_schema.json for algorithmic skill matching
_TAG_TAXONOMY: dict[str, list[str]] = {
    "cloud": ["aws", "azure", "gcp", "terraform", "cloudformation", "iac", "serverless", "hybrid-cloud", "cloud"],
    "ai_ml": ["genai", "rag", "ai", "ml", "sagemaker", "recommendation-engine", "nlp", "llm"],
    "data": ["data", "snowflake", "databricks", "kafka", "spark", "analytics", "data-platform", "data-streaming"],
    "architecture": ["architecture", "microservices", "api", "rest", "graphql", "c4", "adr", "well-architected", "ddd"],
    "delivery": ["delivery", "agile", "safe", "scrum", "kanban", "programme-management", "project-management"],
    "leadership": ["leadership", "stakeholder-management", "governance", "client-delivery", "consulting"],
    "devops": ["devops", "cicd", "terraform", "iac", "docker", "kubernetes", "automation"],
    "cost_saving": ["cost-saving", "revenue", "efficiency"],
}


def _text_to_lower(text: str) -> str:
    return text.lower()


def _validate_url(url: str) -> None:
    """Validate that a URL is safe to fetch — blocks SSRF attack vectors.

    Raises ValueError for non-http/https schemes and for hostnames that
    resolve to private, loopback, or link-local addresses.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Only http/https URLs are allowed, got scheme: '{parsed.scheme}'")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve hostname '{hostname}': {exc}") from exc
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise ValueError(
                f"SSRF blocked: '{hostname}' resolves to private/reserved IP {ip}"
            )


class JDAnalyser:
    """Analyses job descriptions using the Claude API."""

    def __init__(self, claude_client: LLMClient) -> None:
        self._client = claude_client

    async def analyse(self, job_description: str, job_url: str | None = None) -> JDAnalysisResult:
        """Analyse a raw job description text.

        Args:
            job_description: The full JD text to analyse.
            job_url: Optional URL to fetch the JD from if text not provided.

        Returns:
            Structured JDAnalysisResult.
        """
        if not job_description and job_url:
            job_description = await self._fetch_jd(job_url)

        system_prompt, user_prompt = _split_jinja_output(
            render_prompt(
                "jd_analysis.j2",
                job_description=job_description,
                prompt_contract=prompt_contract_block("jd_analysis"),
            )
        )
        telemetry = get_telemetry()
        workflow = telemetry.current_workflow("job_discovery_import")
        started = time.monotonic()
        with telemetry.stage_span(workflow, "prepare_input"):
            try:
                raw: dict[str, Any] = await self._client.complete_json(
                    system_prompt,
                    user_prompt,
                    max_tokens=JD_ANALYSIS.max_output,
                )
            except Exception:
                telemetry.record_model_call(
                    workflow=workflow,
                    provider=type(self._client).__name__,
                    model_id=str(getattr(self._client, "model", "configured")),
                    duration_ms=(time.monotonic() - started) * 1000,
                    outcome="failed",
                )
                raise
            telemetry.record_model_call(
                workflow=workflow,
                provider=type(self._client).__name__,
                model_id=str(getattr(self._client, "model", "configured")),
                duration_ms=(time.monotonic() - started) * 1000,
            )
        return _parse_jd_analysis(
            _ground_jd_analysis(raw, job_description),
            len(job_description),
        )

    async def analyse_from_job_posting(self, job_id: str, db: AsyncSession) -> JDAnalysisResult:
        """Load a JobPosting from DB and analyse its description.

        Args:
            job_id: UUID of the JobPosting record.
            db: Active async SQLAlchemy session.

        Returns:
            JDAnalysisResult for the job.
        """
        from ..models.job import JobPosting
        from sqlalchemy import select

        result = await db.execute(select(JobPosting).where(JobPosting.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            raise ValueError(f"Job posting {job_id} not found")

        description = job.description or job.title or ""
        return await self.analyse(description)

    def compute_skill_match(self, jd_analysis: JDAnalysisResult, master_cv: dict[str, Any]) -> SkillMatchResult:
        """Pure algorithmic skill matching using tag_taxonomy.

        Args:
            jd_analysis: Parsed JD analysis with ATS keywords.
            master_cv: Loaded master_cv_schema dict.

        Returns:
            SkillMatchResult with matched/missing lists and percentage.
        """
        # Flatten all JD keywords
        jd_kws = (
            jd_analysis.ats_keywords.technical
            + jd_analysis.ats_keywords.methodologies
            + jd_analysis.ats_keywords.domain
            + jd_analysis.ats_keywords.certifications
        )
        # Flatten CV skills from all categories (handle both dict and list formats)
        cv_skills: set[str] = set()
        raw_skills = master_cv.get("skills", {})
        skill_cats = raw_skills.values() if isinstance(raw_skills, dict) else (raw_skills if isinstance(raw_skills, list) else [])
        for skill_cat in skill_cats:
            if not isinstance(skill_cat, dict):
                continue
            for item in skill_cat.get("items", []):
                if isinstance(item, str):
                    cv_skills.add(item.lower())
        # Also add tags from experience achievements
        for exp in master_cv.get("experience", []):
            if not isinstance(exp, dict):
                continue
            for ach in exp.get("achievements", []):
                if not isinstance(ach, dict):
                    continue
                for tag in ach.get("tags", []):
                    cv_skills.add(tag.lower())

        matched = [kw for kw in jd_kws if kw.lower() in cv_skills or _fuzzy_in(kw, cv_skills)]
        missing = [kw for kw in jd_kws if kw not in matched]

        match_pct = (len(matched) / len(jd_kws) * 100) if jd_kws else 0.0

        # Domain match: check if JD domain keywords overlap with CV sectors
        cv_sectors = {exp.get("sector", "") for exp in master_cv.get("experience", []) if isinstance(exp, dict)}
        domain_match = bool(
            jd_analysis.company_context.sector
            and any(
                jd_analysis.company_context.sector.lower() in s or s in jd_analysis.company_context.sector.lower()
                for s in cv_sectors
            )
        )

        recommendations = []
        if missing:
            recommendations.append(f"Highlight experience with: {', '.join(missing[:5])}")
        if not domain_match and jd_analysis.company_context.sector:
            recommendations.append(f"Emphasise transferable skills for {jd_analysis.company_context.sector} sector")

        return SkillMatchResult(
            matched=matched,
            missing=missing,
            match_pct=round(match_pct, 1),
            domain_match=domain_match,
            recommendations=recommendations,
        )

    async def _fetch_jd(self, url: str) -> str:
        """Fetch job description text from a URL.

        Args:
            url: The job posting URL.

        Returns:
            Extracted plain text content.
        """
        _validate_url(url)  # raises ValueError on SSRF attempt — must not be caught below
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "lxml")
                # Remove script/style tags
                for tag in soup(["script", "style", "nav", "footer"]):
                    tag.decompose()
                return soup.get_text(separator="\n", strip=True)[:8000]
        except ValueError:
            raise  # re-raise SSRF validation errors
        except Exception as exc:
            logger.warning("Failed to fetch JD from %s: %s", url, exc)
            return ""


def _fuzzy_in(keyword: str, cv_skills: set[str]) -> bool:
    """Simple substring check as a lightweight fuzzy match fallback."""
    kw_lower = keyword.lower()
    return any(kw_lower in skill or skill in kw_lower for skill in cv_skills)


def _split_jinja_output(rendered: str) -> tuple[str, str]:
    """Split a rendered prompt template into (system, user) parts.

    Expects template to emit lines with SYSTEM: and USER: markers.
    Falls back to treating the full output as user prompt.
    """
    system_lines: list[str] = []
    user_lines: list[str] = []
    current = "user"

    for line in rendered.splitlines():
        stripped = line.strip()
        if stripped == "SYSTEM:":
            current = "system"
            continue
        if stripped == "USER:":
            current = "user"
            continue
        if current == "system":
            system_lines.append(line)
        else:
            user_lines.append(line)

    system = "\n".join(system_lines).strip()
    user = "\n".join(user_lines).strip()

    if not system:
        # Treat everything as user; use a generic system prompt
        system = "You are an expert technical recruiter and career coach."
        user = rendered.strip()

    return system, user


def _parse_jd_analysis(raw: dict[str, Any], text_length: int) -> JDAnalysisResult:
    """Convert raw Claude JSON dict into a validated JDAnalysisResult.

    Args:
        raw: The dict returned by Claude.
        text_length: Length of the original JD text for metadata.

    Returns:
        Validated JDAnalysisResult.
    """
    from ..schemas.tailor import (
        CompanyContext,
        ContractDetails,
        Requirements,
        ToneAnalysis,
    )

    def _get(d: dict[str, Any], key: str, default: Any = None) -> Any:
        return d.get(key, default)

    contract = ContractDetails(**{k: v for k, v in _get(raw, "contract_details", {}).items()
                                  if k in ContractDetails.model_fields})
    company = CompanyContext(**{k: v for k, v in _get(raw, "company_context", {}).items()
                                if k in CompanyContext.model_fields})
    reqs_raw = _get(raw, "requirements", {})
    requirements = Requirements(
        must_have=reqs_raw.get("must_have", []),
        nice_to_have=reqs_raw.get("nice_to_have", []),
        years_experience=reqs_raw.get("years_experience"),
    )
    kws_raw = _get(raw, "ats_keywords", {})
    ats_keywords = ATSKeywords(
        technical=kws_raw.get("technical", []),
        methodologies=kws_raw.get("methodologies", []),
        soft_skills=kws_raw.get("soft_skills", []),
        domain=kws_raw.get("domain", []),
        certifications=kws_raw.get("certifications", []),
    )
    tone_raw = _get(raw, "tone_analysis", {})
    tone = ToneAnalysis(
        formality=tone_raw.get("formality", "professional"),
        emphasis=tone_raw.get("emphasis", "technical"),
        red_flags=tone_raw.get("red_flags", []),
    )

    return JDAnalysisResult(
        role_title=_get(raw, "role_title", "Unknown Role"),
        seniority_level=_get(raw, "seniority_level"),
        contract_details=contract,
        company_context=company,
        requirements=requirements,
        responsibilities=_get(raw, "responsibilities", []),
        ats_keywords=ats_keywords,
        tone_analysis=tone,
        raw_text_length=text_length,
    )


def _ground_jd_analysis(
    raw: dict[str, Any],
    job_description: str,
) -> dict[str, Any]:
    """Clear sensitive scalar fields that are not explicit in the JD."""
    grounded = deepcopy(raw)
    contract = grounded.get("contract_details")
    if isinstance(contract, dict):
        for field in (
            "contract_type",
            "rate_range",
            "ir35_status",
            "duration",
            "location",
            "remote_policy",
            "start_date",
        ):
            value = contract.get(field)
            if value is not None and not source_contains(
                str(value),
                job_description,
            ):
                contract[field] = None

    company = grounded.get("company_context")
    if isinstance(company, dict):
        for field in ("company_name", "size"):
            value = company.get(field)
            if value is not None and not source_contains(
                str(value),
                job_description,
            ):
                company[field] = None

    requirements = grounded.get("requirements")
    if isinstance(requirements, dict):
        years = requirements.get("years_experience")
        if years is not None and not source_contains(
            str(years),
            job_description,
        ):
            requirements["years_experience"] = None
    return grounded
