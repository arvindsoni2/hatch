"""Feedback Generator — produces comprehensive session feedback reports via Claude."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ..prompts import render_prompt
from ..schemas.coach import (
    AnswerEvaluation,
    PracticePlanDay,
    QuestionEvaluationSummary,
    SessionFeedbackReport,
)
from .claude_client import ClaudeClient
from .jd_analyser import _split_jinja_output
from .master_cv_store import load_master_cv

logger = logging.getLogger(__name__)


def _load_candidate_name() -> str:
    try:
        cv = load_master_cv()
        return cv.get("personal", {}).get("full_name", "Candidate")
    except Exception:
        return "Candidate"


class FeedbackGeneratorService:
    """Generates comprehensive post-session feedback reports."""

    def __init__(self, claude_client: ClaudeClient) -> None:
        self._client = claude_client

    async def generate_report(
        self,
        session_id: str,
        role_title: str,
        company_name: str,
        question_evaluations: list[tuple[str, str, str, AnswerEvaluation]],
        speech_summaries: list[dict[str, Any]] | None = None,
    ) -> SessionFeedbackReport:
        """Generate a full session feedback report.

        Args:
            session_id: ID of the interview session.
            role_title: Role being interviewed for.
            company_name: Company name.
            question_evaluations: List of (question_id, question_text, category, AnswerEvaluation) tuples.
            speech_summaries: Optional list of speech metric dicts across answers.

        Returns:
            SessionFeedbackReport with scores, narrative, and practice plan.
        """
        if not question_evaluations:
            return SessionFeedbackReport(
                session_id=session_id,
                overall_score=0.0,
                executive_summary="No answers were recorded in this session.",
            )

        # Compute category scores (mean per category)
        category_scores: dict[str, list[float]] = {}
        all_scores: list[float] = []
        q_summaries: list[dict] = []

        for q_id, q_text, category, eval_ in question_evaluations:
            category_scores.setdefault(category, []).append(eval_.overall)
            all_scores.append(eval_.overall)
            q_summaries.append({
                "question_id": q_id,
                "question_text": q_text,
                "category": category,
                "overall_score": eval_.overall,
                "strengths": eval_.strengths,
                "improvements": eval_.improvements,
            })

        overall = sum(all_scores) / len(all_scores) if all_scores else 0.0
        cat_avg = {cat: sum(scores) / len(scores) for cat, scores in category_scores.items()}

        # Speech summary stats
        speech_summary: dict[str, float] | None = None
        if speech_summaries:
            speech_summary = {
                "avg_fillers": sum(s.get("filler_count", 0) for s in speech_summaries) / len(speech_summaries),
                "avg_wpm": sum(s.get("wpm", 0) for s in speech_summaries) / len(speech_summaries),
                "avg_hedging": sum(s.get("hedging_count", 0) for s in speech_summaries) / len(speech_summaries),
            }

        # Claude narrative generation
        candidate_name = _load_candidate_name()
        system_prompt, user_prompt = _split_jinja_output(
            render_prompt(
                "session_report.j2",
                candidate_name=candidate_name,
                role_title=role_title,
                company_name=company_name,
                session_date=datetime.utcnow().strftime("%d %B %Y"),
                answered_count=len(question_evaluations),
                total_questions=len(question_evaluations),
                overall_score=overall,
                category_scores=cat_avg,
                question_summaries=q_summaries,
                speech_summary=speech_summary,
            )
        )

        try:
            raw = await self._client.complete_json(system_prompt, user_prompt, max_tokens=4096)
        except Exception as exc:
            logger.warning("Session report generation failed: %s — using fallback", exc)
            raw = {}

        # Build practice plan
        practice_plan: list[PracticePlanDay] = []
        for day_raw in raw.get("practice_plan", []):
            try:
                practice_plan.append(PracticePlanDay(**day_raw))
            except Exception:
                pass

        # Build question evaluation summaries
        q_eval_summaries = [
            QuestionEvaluationSummary(
                question_id=q["question_id"],
                question_text=q["question_text"],
                category=q["category"],
                overall_score=q["overall_score"],
                scores={},
                strengths=q["strengths"],
                improvements=q["improvements"],
            )
            for q in q_summaries
        ]

        return SessionFeedbackReport(
            session_id=session_id,
            overall_score=round(overall, 1),
            category_scores={k: round(v, 1) for k, v in cat_avg.items()},
            executive_summary=raw.get("executive_summary", f"Session completed with an overall score of {overall:.1f}/10."),
            strengths=raw.get("strengths", []),
            improvement_areas=raw.get("improvement_areas", []),
            coaching_points=raw.get("coaching_points", []),
            practice_plan=practice_plan,
            question_evaluations=q_eval_summaries,
        )
