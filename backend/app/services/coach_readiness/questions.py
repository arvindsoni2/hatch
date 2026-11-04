"""Deterministic likely-question list for a real interview round."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.coach_session import InterviewSession, SessionQuestion
from app.models.question_bank import QuestionBankItem

from .contracts import DebriefQuestion

_BRIEF_LIMIT = 5


def _reference(item: QuestionBankItem, text: str) -> DebriefQuestion:
    return DebriefQuestion(
        id=item.id,
        text=text,
        source_ref={"kind": "question_bank_item", "id": item.id},
    )


async def likely_questions(
    db: AsyncSession,
    application_id: str,
    *,
    limit: int = _BRIEF_LIMIT,
) -> list[DebriefQuestion]:
    """Linked QB items, then role-family items, then the latest session plan."""
    application = await db.get(Application, application_id)
    if application is None or not application.is_active:
        return []

    sessions = (
        await db.execute(
            select(InterviewSession)
            .where(
                InterviewSession.application_id == application_id,
                InterviewSession.deletion_state == "not_requested",
            )
            .order_by(InterviewSession.created_at.desc())
        )
    ).scalars().all()
    role_family = ""
    for session in sessions:
        plan = session.session_plan_json if isinstance(session.session_plan_json, dict) else {}
        role = plan.get("role") if isinstance(plan.get("role"), dict) else {}
        role_family = str(role.get("role_family") or "")
        if role_family:
            break

    items = (
        await db.execute(
            select(QuestionBankItem)
            .where(QuestionBankItem.archived_at.is_(None))
            .order_by(QuestionBankItem.updated_at.desc())
        )
    ).scalars().all()

    selected: list[DebriefQuestion] = []
    seen: set[str] = set()

    def add(question: DebriefQuestion) -> None:
        key = " ".join(question.text.casefold().split())
        if key in seen:
            return
        seen.add(key)
        selected.append(question)

    for item in items:
        if application_id in (item.linked_applications or []):
            text = (item.question or item.title).strip()
            if text:
                add(_reference(item, text))
        if len(selected) >= limit:
            return selected

    for item in items:
        if role_family and item.role_family == role_family:
            text = (item.question or item.title).strip()
            if text:
                add(_reference(item, text))
        if len(selected) >= limit:
            return selected

    if sessions:
        questions = (
            await db.execute(
                select(SessionQuestion)
                .where(SessionQuestion.session_id == sessions[0].id)
                .order_by(SessionQuestion.order_in_session.asc())
            )
        ).scalars().all()
        for question in questions:
            text = question.text.strip()
            if text:
                add(
                    DebriefQuestion(
                        id=f"session:{question.id}",
                        text=text,
                        source_ref=None,
                    )
                )
            if len(selected) >= limit:
                break

    return selected[:limit]
