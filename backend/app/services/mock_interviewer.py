"""Mock Interviewer Service — session flow control and follow-up logic."""
from __future__ import annotations

from ..schemas.coach import AnswerEvaluation, QuestionPresentation

_FOLLOW_UP_THRESHOLD = 6.0


class MockInterviewerService:
    """Controls the question flow during a mock interview session."""

    def get_next_question(
        self,
        questions: list[QuestionPresentation],
        answered_ids: set[str],
    ) -> QuestionPresentation | None:
        """Return the next unanswered question in session order.

        Args:
            questions: All questions in the session (ordered).
            answered_ids: Set of question IDs that have been answered.

        Returns:
            Next QuestionPresentation, or None if session is complete.
        """
        for question in questions:
            if question.id not in answered_ids:
                return question
        return None

    def should_follow_up(self, evaluation: AnswerEvaluation) -> bool:
        """Determine if a follow-up question should be asked.

        Args:
            evaluation: The evaluation for the most recent answer.

        Returns:
            True if a follow-up should be asked (overall score below threshold).
        """
        return evaluation.overall < _FOLLOW_UP_THRESHOLD and evaluation.follow_up_question is not None

    def get_session_progress(
        self,
        total_questions: int,
        answered_count: int,
    ) -> dict[str, int | float]:
        """Return session progress metrics.

        Args:
            total_questions: Total questions in session.
            answered_count: Number of questions answered so far.

        Returns:
            Dict with pct, answered, remaining.
        """
        pct = int((answered_count / total_questions) * 100) if total_questions > 0 else 0
        return {
            "pct": pct,
            "answered": answered_count,
            "remaining": total_questions - answered_count,
            "total": total_questions,
        }
