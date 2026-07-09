"""Question Bank endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas.question_bank import (
    QuestionBankCreate,
    QuestionBankFromInterviewAnswer,
    QuestionBankList,
    QuestionBankRead,
    QuestionBankUpdate,
)
from ..services.question_bank import (
    archive_question_bank_item,
    create_from_interview_answer,
    create_question_bank_item,
    list_question_bank_items,
    read_question_bank_item,
    update_question_bank_item,
)

router = APIRouter(prefix="/api/question-bank", tags=["question-bank"])


@router.get("", response_model=QuestionBankList)
async def list_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(None),
    type: str | None = Query(None),  # noqa: A002 - public query name matches API
    tag: str | None = Query(None),
    skill: str | None = Query(None),
    confidence: str | None = Query(None),
    application_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> QuestionBankList:
    items, total = await list_question_bank_items(
        db,
        skip=skip,
        limit=limit,
        search=search,
        item_type=type,
        tag=tag,
        skill=skill,
        confidence=confidence,
        application_id=application_id,
    )
    return QuestionBankList(items=items, total=total, skip=skip, limit=limit)


@router.post("", response_model=QuestionBankRead, status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: QuestionBankCreate,
    db: AsyncSession = Depends(get_db),
) -> QuestionBankRead:
    try:
        return await create_question_bank_item(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/from-interview-answer", response_model=QuestionBankRead, status_code=status.HTTP_201_CREATED)
async def from_interview_answer(
    payload: QuestionBankFromInterviewAnswer,
    db: AsyncSession = Depends(get_db),
) -> QuestionBankRead:
    try:
        return await create_from_interview_answer(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{item_id}", response_model=QuestionBankRead)
async def get_item(item_id: str, db: AsyncSession = Depends(get_db)) -> QuestionBankRead:
    item = await read_question_bank_item(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Question Bank item not found.")
    return item


@router.patch("/{item_id}", response_model=QuestionBankRead)
async def update_item(
    item_id: str,
    payload: QuestionBankUpdate,
    db: AsyncSession = Depends(get_db),
) -> QuestionBankRead:
    try:
        item = await update_question_bank_item(db, item_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Question Bank item not found.")
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: str, db: AsyncSession = Depends(get_db)) -> Response:
    deleted = await archive_question_bank_item(db, item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Question Bank item not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
