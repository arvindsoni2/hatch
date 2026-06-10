"""TechnicalDrillsService — build worked-example drills for technical interview questions.

For each technical/domain question, calls the LLM to produce a "show don't tell"
worked example walkthrough and a "say it out loud" drill prompt for self-practice.
Gracefully degrades to an empty list if the LLM is unavailable or parsing fails.
"""
from __future__ import annotations

import json
import logging

from ..models.coach_session import SessionQuestion
from ..schemas.coach import TechnicalDrill
from .claude_client import ClaudeClient

logger = logging.getLogger(__name__)

_TECHNICAL_CATEGORIES = {"technical", "domain"}

_SYSTEM_PROMPT = """You are an expert technical interview coach.
Given a technical interview question, produce a concise JSON object with two fields:
- "walkthrough": A worked example with concrete code, architecture, or steps — show, don't tell.
  Include real trade-offs, alternatives considered, and why you chose this approach.
  Max 200 words.
- "drill_prompt": A single sentence telling the candidate to explain their approach
  out loud, as if presenting to an interviewer. E.g. "Explain out loud how you would
  design this system, covering data flow, failure modes, and scaling considerations."

Reply ONLY with valid JSON. No markdown, no preamble.
"""

_USER_TEMPLATE = """Technical interview question:
{question}

Produce the JSON drill object as instructed."""


class TechnicalDrillsService:
    """Build worked-example drills for technical / domain questions."""

    def __init__(self, claude: ClaudeClient) -> None:
        self._claude = claude

    async def build_drills(self, questions: list[SessionQuestion]) -> list[TechnicalDrill]:
        """Build drills for questions in the technical / domain categories.

        Args:
            questions: All questions from the session.

        Returns:
            List of TechnicalDrill objects. Empty list on LLM failure.
        """
        technical_qs = [
            q for q in questions
            if q.category.lower() in _TECHNICAL_CATEGORIES
        ]

        if not technical_qs:
            return []

        drills: list[TechnicalDrill] = []
        for q in technical_qs:
            drill = await self._build_single_drill(q)
            if drill is not None:
                drills.append(drill)

        return drills

    async def _build_single_drill(self, q: SessionQuestion) -> TechnicalDrill | None:
        """Build a single drill; returns None on any failure."""
        try:
            raw = await self._claude.complete(
                system=_SYSTEM_PROMPT,
                user=_USER_TEMPLATE.format(question=q.text),
            )
            data = json.loads(raw)
            return TechnicalDrill(
                question_id=q.id,
                question_text=q.text,
                walkthrough=data["walkthrough"],
                drill_prompt=data["drill_prompt"],
                category=q.category,
            )
        except Exception as exc:
            logger.warning("TechnicalDrillsService: skipping question %s — %s", q.id, exc)
            return None
