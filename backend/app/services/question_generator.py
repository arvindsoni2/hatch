"""Question Generator Service — generates weighted interview questions via Claude."""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from ..prompts import render_prompt
from ..schemas.coach import CompanyResearchResponse, QuestionPresentation, SessionConfig
from .llm_client import LLMClient
from ..agents.tools.context_budgets import QUESTION_GEN
from .jd_analyser import _split_jinja_output
from .master_cv_store import load_master_cv
from .prompt_catalog import prompt_contract_block

logger = logging.getLogger(__name__)

_CATEGORY_WEIGHTS = {
    "Technical": 0.30,
    "Behavioural": 0.25,
    "Situational": 0.15,
    "Domain": 0.10,
    "Culture": 0.10,
    "Commercial": 0.10,
}


def _load_candidate_summary() -> str:
    """Load a condensed candidate summary from the master CV for prompt context."""
    try:
        cv = load_master_cv()
        personal = cv.get("personal", {})
        summary_variants = cv.get("summary_variants", {})
        summary = next(iter(summary_variants.values()), "")
        skills = cv.get("skills", {})
        if isinstance(skills, dict):
            skills_text = "; ".join(
                cat.get("display_name", "") + ": " + ", ".join(cat.get("items", [])[:5])
                for cat in skills.values()
                if isinstance(cat, dict)
            )
        else:
            skills_text = ""
        name = personal.get("full_name", "Candidate")
        return f"{name}\n\nSummary: {summary[:500]}\n\nKey Skills: {skills_text[:500]}"
    except Exception as exc:
        logger.warning("Failed to load master CV for question generation: %s", exc)
        return "Candidate"


class QuestionGeneratorService:
    """Generates weighted interview questions tailored to company and role."""

    def __init__(self, claude_client: LLMClient) -> None:
        self._client = claude_client

    async def generate(
        self,
        config: SessionConfig,
        company_name: str,
        role_title: str,
        company_research: CompanyResearchResponse | None = None,
        jd_text: str | None = None,
    ) -> list[QuestionPresentation]:
        """Generate interview questions for a session.

        Args:
            config: Session configuration (question count, difficulty, etc.).
            company_name: Company name for context.
            role_title: Role being interviewed for.
            company_research: Optional pre-fetched company research.
            jd_text: Optional job description text for context.

        Returns:
            List of QuestionPresentation objects ordered for the session.
        """
        candidate_summary = _load_candidate_summary()
        research_dict = (
            company_research.model_dump(mode="json")
            if company_research
            and company_research.verification_state != "not_verified"
            else {}
        )
        requirements = _build_requirements(jd_text or role_title)

        system_prompt, user_prompt = _split_jinja_output(
            render_prompt(
                "question_generation.j2",
                question_count=config.question_count,
                role_title=role_title,
                company_name=company_name,
                company_research=research_dict,
                jd_text=jd_text or "",
                candidate_summary=candidate_summary,
                difficulty=config.difficulty,
                requirements=requirements,
                prompt_contract=prompt_contract_block("question_generation"),
            )
        )

        raw = await self._client.complete_json(system_prompt, user_prompt, max_tokens=QUESTION_GEN.max_output)

        # Handle both bare array and {"questions": [...]} wrapper
        if isinstance(raw, list):
            questions_raw: list[dict[str, Any]] = raw
        elif isinstance(raw, dict):
            # Try common wrapper keys
            for key in ("questions", "items", "data", "interview_questions"):
                if key in raw and isinstance(raw[key], list):
                    questions_raw = raw[key]
                    break
            else:
                # Last resort: take the first list value found
                questions_raw = next((v for v in raw.values() if isinstance(v, list)), [])
        else:
            questions_raw = []

        if not questions_raw:
            logger.error(
                "No questions extracted for %s/%s — raw response keys: %s",
                company_name, role_title,
                list(raw.keys()) if isinstance(raw, dict) else type(raw).__name__,
            )
            raise ValueError(
                f"LLM returned no questions for {company_name}/{role_title}. "
                "The model may be unavailable or returned an unexpected JSON structure."
            )

        return _parse_questions(
            questions_raw,
            config.question_count,
            tuple(requirement["requirement_id"] for requirement in requirements),
        )


def _build_requirements(source: str) -> list[dict[str, str]]:
    """Build stable requirement IDs from source JD lines or sentences."""
    candidates = [
        value.strip(" \t-*•")
        for value in re.split(r"[\n.!?]+", source)
        if value.strip(" \t-*•")
    ][:12]
    if not candidates:
        candidates = ["Role requirements"]
    return [
        {
            "requirement_id": (
                "requirement-"
                + hashlib.sha256(text.casefold().encode("utf-8")).hexdigest()[:12]
            ),
            "text": text,
        }
        for text in candidates
    ]


def _parse_questions(
    raw_list: list[dict[str, Any]],
    expected_count: int,
    requirement_ids: tuple[str, ...],
) -> list[QuestionPresentation]:
    """Parse and validate raw question list from Claude."""
    questions: list[QuestionPresentation] = []
    seen_questions: set[str] = set()
    allowed_categories = set(_CATEGORY_WEIGHTS)

    for i, q in enumerate(raw_list):
        if not isinstance(q, dict):
            continue
        text = str(q.get("text") or "").strip()
        normalized_text = " ".join(
            re.findall(r"[a-z0-9]+", text.casefold())
        )
        if not normalized_text or normalized_text in seen_questions:
            continue
        seen_questions.add(normalized_text)
        requirement_id = q.get("requirement_id")
        if requirement_id not in requirement_ids:
            requirement_id = requirement_ids[i % len(requirement_ids)]
        category = q.get("category", "Technical")
        if category not in allowed_categories:
            category = "Technical"
        try:
            questions.append(
                QuestionPresentation(
                    id=f"q_{len(questions) + 1}",
                    text=text,
                    category=category,
                    difficulty=q.get("difficulty", "medium"),
                    context=q.get("context"),
                    requirement_id=requirement_id,
                    num=len(questions) + 1,
                    total=expected_count,
                )
            )
        except Exception as exc:
            logger.warning("Failed to parse question %d: %s", i, exc)

    return questions
