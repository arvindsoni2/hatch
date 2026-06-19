"""Cover Letter Generator — produces tailored cover letters via Claude."""
from __future__ import annotations

import logging
import re
from typing import Any

from pathlib import Path

from ..prompts import render_prompt
from ..schemas.tailor import CoverLetterResult, JDAnalysisResult, TailoredCVResult
from ..skills.skill_loader import SkillLoader, SkillRegistry
from .llm_client import LLMClient
from ..agents.tools.context_budgets import CL_BODY, CL_SNIPPET
from .jd_analyser import _split_jinja_output

logger = logging.getLogger(__name__)

_MAX_WORDS = 350
_MIN_WORDS = 250
_SKILLS_DIR = Path(__file__).parent.parent / "skills"

_FORMAL_SECTORS = frozenset(
    {"construction", "finance", "government", "energy", "defence", "defense",
     "infrastructure", "utilities", "public sector", "legal", "banking"}
)
_CONVERSATIONAL_SECTORS = frozenset(
    {"technology", "tech", "startup", "creative", "media", "advertising",
     "design", "gaming", "software", "saas"}
)

_NUMERIC_TOKEN_RE = re.compile(
    r"(?:[£$€¥][\d,]+(?:\.\d+)?(?:[KMBkm+]*)|"
    r"\d[\d,]*(?:\.\d+)?(?:[KMBkm%+]+))",
    re.IGNORECASE,
)
_PLACEHOLDER_RE = re.compile(r"\[[^\]]+\]|\bPLACEHOLDER\b|\bTODO\b", re.IGNORECASE)


def select_tone_variant(jd_analysis: "JDAnalysisResult") -> str:
    """Return 'A' (formal) or 'B' (conversational) based on JD sector.

    Formal sectors (A): construction, finance, government, energy, defence.
    Conversational sectors (B): tech, startup, creative.
    Defaults to 'A' when sector is absent or unrecognised.
    """
    sector = (getattr(jd_analysis, "sector", None) or "").lower()
    if any(s in sector for s in _CONVERSATIONAL_SECTORS):
        return "B"
    return "A"


def _default_skill_loader() -> SkillLoader:
    return SkillLoader(SkillRegistry(_SKILLS_DIR))


class CoverLetterGenerator:
    """Generates and refines cover letters for job applications."""

    def __init__(self, claude_client: LLMClient, skill_loader: SkillLoader | None = None) -> None:
        self._client = claude_client
        self._skill_loader = skill_loader or _default_skill_loader()

    async def generate(
        self,
        jd_analysis: JDAnalysisResult,
        tailored_cv: TailoredCVResult,
        personal: dict[str, Any],
        variant: str = "A",
    ) -> CoverLetterResult:
        """Generate a cover letter for the given JD and tailored CV.

        Args:
            jd_analysis: Parsed JD analysis.
            tailored_cv: CV tailored to the JD.
            personal: Personal details dict from master CV.
            variant: "A" (formal) or "B" (conversational).

        Returns:
            CoverLetterResult, trimmed to <= 350 words.
        """
        skill_instructions = self._skill_loader.instructions("cover-letter")

        system_prompt, user_prompt = _split_jinja_output(
            render_prompt(
                "cl_generation.j2",
                jd_analysis=jd_analysis.model_dump(),
                tailored_cv=tailored_cv.model_dump(),
                personal=personal,
                variant=variant,
                skill_instructions=skill_instructions,
            )
        )
        raw: dict[str, Any] = await self._client.complete_json(system_prompt, user_prompt, max_tokens=CL_BODY.max_output)
        result = _parse_cover_letter(raw)
        result.grounding_issues = _validate_cover_letter_grounding(result, tailored_cv, personal)

        # Trim loop: if over word limit, regenerate with tighter instruction
        if result.word_count > _MAX_WORDS:
            logger.info("Cover letter %d words — trimming (variant %s)", result.word_count, variant)
            system_prompt2, user_prompt2 = _split_jinja_output(
                render_prompt(
                    "cl_generation.j2",
                    jd_analysis=jd_analysis.model_dump(),
                    tailored_cv=tailored_cv.model_dump(),
                    personal=personal,
                    variant=variant,
                    trim_instruction=f"The previous draft was {result.word_count} words. "
                    f"STRICTLY keep total body to {_MAX_WORDS} words max.",
                )
            )
            raw2: dict[str, Any] = await self._client.complete_json(system_prompt2, user_prompt2, max_tokens=CL_BODY.max_output)
            result = _parse_cover_letter(raw2)
            result.grounding_issues = _validate_cover_letter_grounding(result, tailored_cv, personal)

        return result

    async def regenerate_paragraph(
        self,
        paragraph_index: int,
        instruction: str,
        current_letter: CoverLetterResult,
        jd_analysis: JDAnalysisResult,
    ) -> CoverLetterResult:
        """Regenerate a single paragraph of an existing cover letter.

        Args:
            paragraph_index: 0-3 index of the paragraph to replace.
            instruction: User guidance for the regeneration.
            current_letter: The current full cover letter.
            jd_analysis: JD analysis for context.

        Returns:
            Updated CoverLetterResult with the new paragraph.
        """
        system = (
            "You are an expert cover letter writer. Rewrite only the specified paragraph "
            "keeping the rest of the letter context in mind. Return JSON with key 'paragraph'."
        )
        paragraphs = current_letter.body_paragraphs
        current_para = paragraphs[paragraph_index] if paragraph_index < len(paragraphs) else ""

        user = (
            f"Current paragraph {paragraph_index + 1}:\n{current_para}\n\n"
            f"Instruction: {instruction}\n\n"
            f"JD role: {jd_analysis.role_title}\n"
            f"Key keywords: {', '.join(jd_analysis.ats_keywords.technical[:10])}\n\n"
            f"Return JSON: {{\"paragraph\": \"<rewritten paragraph>\"}}"
        )
        raw: dict[str, Any] = await self._client.complete_json(system, user, max_tokens=CL_SNIPPET.max_output)
        new_para = raw.get("paragraph", current_para)

        new_paragraphs = list(paragraphs)
        if paragraph_index < len(new_paragraphs):
            new_paragraphs[paragraph_index] = new_para
        else:
            new_paragraphs.append(new_para)

        full_text = " ".join(new_paragraphs)
        word_count = len(full_text.split())

        return CoverLetterResult(
            subject_line=current_letter.subject_line,
            greeting=current_letter.greeting,
            body_paragraphs=new_paragraphs,
            sign_off=current_letter.sign_off,
            word_count=word_count,
            key_keywords_used=current_letter.key_keywords_used,
            grounding_issues=list(current_letter.grounding_issues),
        )


def _parse_cover_letter(raw: dict[str, Any]) -> CoverLetterResult:
    """Convert raw Claude JSON into CoverLetterResult."""
    paragraphs: list[str] = raw.get("body_paragraphs", [])
    full_text = " ".join(paragraphs)
    word_count = raw.get("word_count") or len(full_text.split())

    return CoverLetterResult(
        subject_line=raw.get("subject_line", "Application"),
        greeting=raw.get("greeting", "Dear Hiring Manager,"),
        body_paragraphs=paragraphs,
        sign_off=raw.get("sign_off", "Yours sincerely,"),
        word_count=word_count,
        key_keywords_used=raw.get("key_keywords_used", []),
        grounding_issues=raw.get("grounding_issues", []),
    )


def _source_text(tailored_cv: TailoredCVResult, personal: dict[str, Any]) -> str:
    parts: list[str] = []
    parts.append(tailored_cv.summary)
    for skill_group in tailored_cv.skills:
        if isinstance(skill_group, dict):
            parts.append(str(skill_group.get("category") or skill_group.get("display_name") or ""))
            parts.extend(str(item) for item in skill_group.get("items", []) if item)
    for exp in tailored_cv.experience:
        parts.extend([exp.role, exp.company, exp.period])
        parts.extend(exp.achievements)
    for edu in getattr(tailored_cv, "education", []):
        parts.extend([
            getattr(edu, "qualification", ""),
            getattr(edu, "field", ""),
            getattr(edu, "institution", ""),
            getattr(edu, "year", ""),
        ])
        parts.extend(getattr(edu, "details", []) or [])
    parts.extend(tailored_cv.certifications)
    parts.extend(str(value) for value in personal.values() if value)
    return " ".join(parts).lower()


def _validate_cover_letter_grounding(
    result: CoverLetterResult,
    tailored_cv: TailoredCVResult,
    personal: dict[str, Any],
) -> list[str]:
    text = " ".join(
        [result.subject_line, result.greeting, result.sign_off] + result.body_paragraphs
    )
    source = _source_text(tailored_cv, personal)
    issues: list[str] = []
    if _PLACEHOLDER_RE.search(text):
        issues.append("Cover letter contains placeholder text.")
    for token in _NUMERIC_TOKEN_RE.findall(text):
        if token.lower() not in source:
            issues.append(f"Cover letter numeric token '{token}' is not grounded in the tailored CV.")
    return issues
