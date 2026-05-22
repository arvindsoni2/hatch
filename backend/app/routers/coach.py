"""FastAPI router for the Coach module — mock interview practice sessions."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas.coach import (
    AnswerEvaluation,
    CompanyResearchResponse,
    CreateSessionRequest,
    QuestionPresentation,
    SessionFeedbackReport,
    SessionListItem,
    SessionResponse,
    SubmitAnswerRequest,
)
from ..services.coach_service import CoachService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/coach", tags=["coach"])


def get_coach_service() -> CoachService:
    """Dependency factory for CoachService (stateless, re-created per request)."""
    return CoachService()


# ---------------------------------------------------------------------------
# Company Research
# ---------------------------------------------------------------------------


@router.post("/research", response_model=CompanyResearchResponse)
async def research_company(
    company_name: str = Query(..., description="Company name to research"),
    sector: Optional[str] = Query(None, description="Optional sector hint"),
    db: AsyncSession = Depends(get_db),
    svc: CoachService = Depends(get_coach_service),
) -> CompanyResearchResponse:
    """Research a company (cached 30 days). Returns description, news, tech stack signals."""
    try:
        return await svc.research_company(company_name, sector, db)
    except Exception as exc:
        logger.error("research_company failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/research/{company_name}", response_model=CompanyResearchResponse)
async def get_company_research(
    company_name: str,
    db: AsyncSession = Depends(get_db),
    svc: CoachService = Depends(get_coach_service),
) -> CompanyResearchResponse:
    """Return cached company research. Returns 404 if no valid cache entry exists."""
    from ..repositories.research_repository import ResearchRepository
    repo = ResearchRepository(db)
    cached = await repo.get_cached(company_name)
    if not cached:
        raise HTTPException(status_code=404, detail="No cached research found for this company")
    return CompanyResearchResponse(
        company_name=cached.company_name,
        sector=cached.sector,
        website=cached.website,
        description=cached.description,
        recent_news=cached.recent_news or [],
        key_products=cached.key_products or [],
        tech_stack_signals=cached.tech_stack_signals or [],
    )


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(
    request: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
    svc: CoachService = Depends(get_coach_service),
) -> SessionResponse:
    """Create a new mock interview session. Pre-generates all questions and model answers."""
    try:
        return await svc.create_session(request, db)
    except Exception as exc:
        logger.error("create_session failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/sessions", response_model=list[SessionListItem])
async def list_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(None, description="Filter by status: setup|active|completed|abandoned"),
    db: AsyncSession = Depends(get_db),
    svc: CoachService = Depends(get_coach_service),
) -> list[SessionListItem]:
    """List interview sessions, newest first."""
    return await svc.list_sessions(db, limit=limit, status=status)


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    svc: CoachService = Depends(get_coach_service),
) -> SessionResponse:
    """Get a session with all its questions."""
    return await svc.get_session(session_id, db)


@router.delete("/sessions/{session_id}", status_code=204, response_class=Response)
async def abandon_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    svc: CoachService = Depends(get_coach_service),
) -> Response:
    """Mark a session as abandoned."""
    from ..repositories.session_repository import SessionRepository
    repo = SessionRepository(db)
    session = await repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await repo.update_session_status(session_id, "abandoned")
    await db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}/next-question", response_model=Optional[QuestionPresentation])
async def get_next_question(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    svc: CoachService = Depends(get_coach_service),
) -> QuestionPresentation | None:
    """Return the next unanswered question in the session, or null if complete."""
    return await svc.get_next_question(session_id, db)


@router.post("/sessions/{session_id}/skip", status_code=204, response_class=Response)
async def skip_question(
    session_id: str,
    question_id: str = Query(..., description="ID of the question to skip"),
    db: AsyncSession = Depends(get_db),
    svc: CoachService = Depends(get_coach_service),
) -> Response:
    """Skip a question by recording an empty answer (so it counts as answered)."""
    from ..repositories.session_repository import SessionRepository
    repo = SessionRepository(db)
    question = await repo.get_question(question_id)
    if not question or question.session_id != session_id:
        raise HTTPException(status_code=404, detail="Question not found in this session")
    await repo.save_recording(
        session_id=session_id,
        question_id=question_id,
        recording_type="text",
        transcript="[SKIPPED]",
        speech_metrics=None,
        video_metrics=None,
        evaluation_json=None,
    )
    await db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Answer submission
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/submit-answer", response_model=AnswerEvaluation)
async def submit_answer(
    session_id: str,
    question_id: str = Query(..., description="ID of the question being answered"),
    request: SubmitAnswerRequest = ...,
    db: AsyncSession = Depends(get_db),
    svc: CoachService = Depends(get_coach_service),
) -> AnswerEvaluation:
    """Submit a transcript for evaluation. Returns STAR-rubric scores and coaching feedback."""
    try:
        return await svc.submit_answer(session_id, question_id, request, db)
    except Exception as exc:
        logger.error("submit_answer failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/end", response_model=SessionFeedbackReport)
async def end_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    svc: CoachService = Depends(get_coach_service),
) -> SessionFeedbackReport:
    """End a session and generate the comprehensive feedback report."""
    try:
        return await svc.end_session(session_id, db)
    except Exception as exc:
        logger.error("end_session failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/report", response_model=SessionFeedbackReport)
async def get_session_report(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    svc: CoachService = Depends(get_coach_service),
) -> SessionFeedbackReport:
    """Return the feedback report for a completed session."""
    return await svc.get_report(session_id, db)


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------


@router.get("/progress/{application_id}", response_model=list[SessionListItem])
async def get_application_progress(
    application_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[SessionListItem]:
    """List all sessions for a given application (interview prep history)."""
    from sqlalchemy import select
    from ..models.coach_session import InterviewSession
    from ..schemas.coach import SessionListItem

    result = await db.execute(
        select(InterviewSession)
        .where(InterviewSession.application_id == application_id)
        .order_by(InterviewSession.created_at.desc())
    )
    rows = result.scalars().all()
    return [
        SessionListItem(
            id=r.id,
            company_name=r.company_name,
            role_title=r.role_title,
            status=r.status,
            overall_score=r.overall_score,
            created_at=r.created_at,
        )
        for r in rows
    ]
