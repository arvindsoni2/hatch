"""Question Bank service helpers."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.application import Application
from ..models.coach_session import InterviewSession, SessionQuestion
from ..models.question_bank import QuestionBankItem
from ..schemas.question_bank import (
    QuestionBankCreate,
    QuestionBankFromInterviewAnswer,
    QuestionBankRead,
    QuestionBankUpdate,
)


def _now() -> datetime:
    return datetime.utcnow()


def _list(value: list[str] | None) -> list[str]:
    return value or []


def _read(row: QuestionBankItem) -> QuestionBankRead:
    data = {
        column.name: getattr(row, column.name)
        for column in QuestionBankItem.__table__.columns
    }
    data["skills"] = _list(row.skills)
    data["tags"] = _list(row.tags)
    data["linked_applications"] = _list(row.linked_applications)
    return QuestionBankRead.model_validate(data)


async def create_question_bank_item(db: AsyncSession, payload: QuestionBankCreate) -> QuestionBankRead:
    await _validate_linked_applications(db, payload.linked_applications or [])
    row = QuestionBankItem(**payload.model_dump())
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return _read(row)


async def list_question_bank_items(
    db: AsyncSession,
    *,
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    item_type: str | None = None,
    tag: str | None = None,
    skill: str | None = None,
    confidence: str | None = None,
    application_id: str | None = None,
) -> tuple[list[QuestionBankRead], int]:
    result = await db.execute(
        select(QuestionBankItem)
        .where(QuestionBankItem.archived_at.is_(None))
        .order_by(QuestionBankItem.updated_at.desc())
    )
    rows = list(result.scalars().all())
    needle = search.strip().lower() if search else None
    if needle:
        rows = [row for row in rows if _matches_search(row, needle)]
    if item_type:
        rows = [row for row in rows if row.type == item_type]
    if confidence:
        rows = [row for row in rows if row.confidence == confidence]
    if tag:
        rows = [row for row in rows if tag in _list(row.tags)]
    if skill:
        rows = [row for row in rows if skill in _list(row.skills)]
    if application_id:
        rows = [row for row in rows if application_id in _list(row.linked_applications)]

    total = len(rows)
    return [_read(row) for row in rows[skip : skip + limit]], total


async def get_question_bank_item(db: AsyncSession, item_id: str) -> QuestionBankItem | None:
    result = await db.execute(
        select(QuestionBankItem).where(
            QuestionBankItem.id == item_id,
            QuestionBankItem.archived_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def read_question_bank_item(db: AsyncSession, item_id: str) -> QuestionBankRead | None:
    row = await get_question_bank_item(db, item_id)
    return _read(row) if row else None


async def update_question_bank_item(
    db: AsyncSession,
    item_id: str,
    payload: QuestionBankUpdate,
) -> QuestionBankRead | None:
    row = await get_question_bank_item(db, item_id)
    if row is None:
        return None
    data = payload.model_dump(exclude_unset=True)
    if "linked_applications" in data:
        await _validate_linked_applications(db, data["linked_applications"] or [])
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_at = _now()
    await db.flush()
    await db.refresh(row)
    return _read(row)


async def archive_question_bank_item(db: AsyncSession, item_id: str) -> bool:
    row = await get_question_bank_item(db, item_id)
    if row is None:
        return False
    row.archived_at = _now()
    row.updated_at = row.archived_at
    await db.flush()
    return True


async def create_from_interview_answer(
    db: AsyncSession,
    payload: QuestionBankFromInterviewAnswer,
) -> QuestionBankRead:
    result = await db.execute(
        select(SessionQuestion, InterviewSession)
        .join(InterviewSession, SessionQuestion.session_id == InterviewSession.id)
        .where(
            SessionQuestion.id == payload.question_id,
            InterviewSession.id == payload.session_id,
        )
    )
    row = result.first()
    if row is None:
        raise ValueError("Interview question not found.")
    question, session = row
    linked = [session.application_id] if session.application_id else []
    title = payload.title or question.text[:120]
    item = QuestionBankItem(
        type="interview_question",
        question=question.text,
        title=title,
        answer_draft=payload.answer_draft.strip(),
        situation=payload.situation,
        task=payload.task,
        action=payload.action,
        result=payload.result,
        skills=payload.skills or [],
        tags=payload.tags or [],
        linked_applications=linked,
        source="interview_prep",
        confidence=payload.confidence,
        source_session_id=session.id,
        source_question_id=question.id,
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return _read(item)


async def _validate_linked_applications(db: AsyncSession, application_ids: list[str]) -> None:
    if not application_ids:
        return
    result = await db.execute(select(Application.id).where(Application.id.in_(application_ids)))
    found = {row[0] for row in result.all()}
    missing = sorted(set(application_ids) - found)
    if missing:
        raise ValueError(f"Unknown application id: {missing[0]}")


def _matches_search(row: QuestionBankItem, needle: str) -> bool:
    haystacks = [
        row.title,
        row.question,
        row.answer_draft,
        row.situation,
        row.task,
        row.action,
        row.result,
        row.seniority,
        row.role_family,
        " ".join(_list(row.tags)),
        " ".join(_list(row.skills)),
    ]
    return any(needle in str(value or "").lower() for value in haystacks)
