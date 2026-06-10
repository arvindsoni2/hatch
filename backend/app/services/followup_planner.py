"""FollowUpPlannerService — create follow-up sessions targeting weakest rubric dimensions.

Identifies the 1-2 weakest dimensions from the session rubric and creates a new
InterviewSession with those as focus_areas and parent_session_id pointing back.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.coach_session import InterviewSession, SessionQuestion
from ..schemas.coach import SessionRubric

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.utcnow()


class FollowUpPlannerService:
    """Create follow-up sessions targeting the weakest rubric dimensions."""

    async def plan(
        self,
        parent_session: InterviewSession,
        rubric: SessionRubric,
        db: AsyncSession,
    ) -> tuple[str, list[str]]:
        """Create a follow-up session targeting weakest dimensions.

        Args:
            parent_session: The completed parent session.
            rubric: The session rubric with per-dimension scores.
            db: Active DB session.

        Returns:
            (new_session_id, focus_areas) tuple.
        """
        # Identify 1-2 weakest dimensions
        if rubric.dimensions:
            sorted_dims = sorted(
                rubric.dimensions.items(), key=lambda kv: kv[1].score
            )
            focus_areas = [name for name, _ in sorted_dims[:2]]
        else:
            focus_areas = []

        # Create a new child session
        new_session = InterviewSession(
            id=str(uuid.uuid4()),
            application_id=parent_session.application_id,
            company_name=parent_session.company_name,
            role_title=parent_session.role_title,
            config=parent_session.config,
            status="setup",
            parent_session_id=parent_session.id,
            focus_areas=focus_areas,
            coach_mode=parent_session.coach_mode,
            started_at=_utcnow(),
            created_at=_utcnow(),
        )
        db.add(new_session)
        await db.flush()
        await db.refresh(new_session)

        # Copy questions from parent session (fresh recordings, same question set)
        from sqlalchemy import select  # noqa: PLC0415
        result = await db.execute(
            select(SessionQuestion)
            .where(SessionQuestion.session_id == parent_session.id)
            .order_by(SessionQuestion.order_in_session)
        )
        parent_questions = list(result.scalars().all())

        for pq in parent_questions:
            new_q = SessionQuestion(
                id=str(uuid.uuid4()),
                session_id=new_session.id,
                question_num=pq.question_num,
                text=pq.text,
                category=pq.category,
                difficulty=pq.difficulty,
                context=pq.context,
                model_answer=pq.model_answer,
                order_in_session=pq.order_in_session,
            )
            db.add(new_q)

        await db.flush()
        await db.refresh(new_session)

        logger.info(
            "FollowUpPlannerService: created session %s (parent=%s, focus=%s)",
            new_session.id,
            parent_session.id,
            focus_areas,
        )
        return new_session.id, focus_areas
