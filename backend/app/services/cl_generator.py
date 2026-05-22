"""Cover Letter Generator — produces tailored cover letters via Claude."""
from __future__ import annotations

import logging
from typing import Any

from ..prompts import render_prompt
from ..schemas.tailor import CoverLetterResult, JDAnalysisResult, TailoredCVResult
from .claude_client import ClaudeClient
from .jd_analyser import _split_jinja_output

logger = logging.getLogger(__name__)

_MAX_WORDS = 350
_MIN_WORDS = 250


class CoverLetterGenerator:
    """Generates and refines cover letters for job applications."""

    def __init__(self, claude_client: ClaudeClient) -> None:
        self._client = claude_client

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
        system_prompt, user_prompt = _split_jinja_output(
            render_prompt(
                "cl_generation.j2",
                jd_analysis=jd_analysis.model_dump(),
                tailored_cv=tailored_cv.model_dump(),
                personal=personal,
                variant=variant,
            )
        )
        raw: dict[str, Any] = await self._client.complete_json(system_prompt, user_prompt, max_tokens=2048)
        result = _parse_cover_letter(raw)

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
            raw2: dict[str, Any] = await self._client.complete_json(system_prompt2, user_prompt2, max_tokens=2048)
            result = _parse_cover_letter(raw2)

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
        raw: dict[str, Any] = await self._client.complete_json(system, user, max_tokens=512)
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
    )
