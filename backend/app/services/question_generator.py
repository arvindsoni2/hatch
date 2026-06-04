"""Question Generator Service — generates weighted interview questions via Claude."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..prompts import render_prompt
from ..schemas.coach import CompanyResearchResponse, QuestionPresentation, SessionConfig
from .claude_client import ClaudeClient
from .jd_analyser import _split_jinja_output

logger = logging.getLogger(__name__)

_MASTER_CV_PATH = Path(__file__).parent.parent / "templates" / "master_cv.json"

_CATEGORY_WEIGHTS = {
    "Technical": 0.30,
    "Behavioural": 0.25,
    "Situational": 0.15,
    "Domain": 0.10,
    "Culture": 0.10,
    "Commercial": 0.10,
}


def _load_candidate_summary() -> str:
    """Load a condensed candidate summary from master CV for prompt context."""
    try:
        with _MASTER_CV_PATH.open() as fh:
            cv = json.load(fh)
        personal = cv.get("personal", {})
        summary_variants = cv.get("summary_variants", {})
        summary = next(iter(summary_variants.values()), "")
        skills_text = "; ".join(
            cat.get("display_name", "") + ": " + ", ".join(cat.get("items", [])[:5])
            for cat in cv.get("skills", {}).values()
        )
        name = personal.get("full_name", "Candidate")
        return f"{name}\n\nSummary: {summary[:500]}\n\nKey Skills: {skills_text[:500]}"
    except Exception as exc:
        logger.warning("Failed to load master CV: %s", exc)
        return "Senior Solutions Architect with 20+ years experience in cloud, data, and AI architectures."


class QuestionGeneratorService:
    """Generates weighted interview questions tailored to company and role."""

    def __init__(self, claude_client: ClaudeClient) -> None:
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
        research_dict = company_research.model_dump() if company_research else {}

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
            )
        )

        raw = await self._client.complete_json(system_prompt, user_prompt, max_tokens=4096)

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

        return _parse_questions(questions_raw, config.question_count)


def _parse_questions(
    raw_list: list[dict[str, Any]],
    expected_count: int,
) -> list[QuestionPresentation]:
    """Parse and validate raw question list from Claude."""
    questions: list[QuestionPresentation] = []
    total = max(len(raw_list), expected_count)

    for i, q in enumerate(raw_list):
        try:
            questions.append(
                QuestionPresentation(
                    id=f"q_{i + 1}",  # temporary ID — replaced by DB ID after persistence
                    text=q.get("text", ""),
                    category=q.get("category", "General"),
                    difficulty=q.get("difficulty", "medium"),
                    context=q.get("context"),
                    num=i + 1,
                    total=total,
                )
            )
        except Exception as exc:
            logger.warning("Failed to parse question %d: %s", i, exc)

    return questions
