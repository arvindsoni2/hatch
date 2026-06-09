"""Coach Service — orchestrates the full interview preparation pipeline."""
from __future__ import annotations

import json
import logging

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

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
from .answer_evaluator import AnswerEvaluatorService
from .claude_client import ClaudeClient
from .company_researcher import CompanyResearchService
from .feedback_generator import FeedbackGeneratorService
from .mock_interviewer import MockInterviewerService
from .model_answer_gen import ModelAnswerGeneratorService
from .question_generator import QuestionGeneratorService, _load_candidate_summary
from .rubric_synthesiser import RubricSynthesiserService
from .speech_analyser import SpeechAnalyserService
from .video_analyser import VideoAnalyserService

logger = logging.getLogger(__name__)


class CoachService:
    """Orchestrates all Coach module services for interview practice sessions."""

    def __init__(self) -> None:
        self._claude = ClaudeClient()
        self._researcher = CompanyResearchService(self._claude)
        self._question_gen = QuestionGeneratorService(self._claude)
        self._model_answer_gen = ModelAnswerGeneratorService(self._claude)
        self._evaluator = AnswerEvaluatorService(self._claude)
        self._speech_analyser = SpeechAnalyserService()
        self._video_analyser = VideoAnalyserService()
        self._mock_interviewer = MockInterviewerService()
        self._feedback_gen = FeedbackGeneratorService(self._claude)
        self._rubric_synthesiser = RubricSynthesiserService()

    async def research_company(
        self, company_name: str, sector: str | None, db: AsyncSession
    ) -> CompanyResearchResponse:
        """Research a company, checking cache first.

        Args:
            company_name: Company to research.
            sector: Optional sector hint.
            db: Active DB session.

        Returns:
            CompanyResearchResponse.
        """
        from ..repositories.research_repository import ResearchRepository
        research_repo = ResearchRepository(db)

        cached = await research_repo.get_cached(company_name)
        if cached:
            logger.info("Cache hit for company research: %s", company_name)
            return CompanyResearchResponse(
                company_name=cached.company_name,
                sector=cached.sector,
                website=cached.website,
                description=cached.description,
                recent_news=cached.recent_news or [],
                key_products=cached.key_products or [],
                tech_stack_signals=cached.tech_stack_signals or [],
            )

        result = await self._researcher.research(company_name, sector)

        await research_repo.save(
            company_name=company_name,
            data={
                "sector": result.sector,
                "website": result.website,
                "description": result.description,
                "recent_news": result.recent_news,
                "key_products": result.key_products,
                "tech_stack_signals": result.tech_stack_signals,
            },
        )
        await db.commit()
        return result

    async def create_session(
        self, request: CreateSessionRequest, db: AsyncSession, session_id: str | None = None
    ) -> SessionResponse:
        """Create a new interview session with pre-generated questions.

        Args:
            request: Session creation request with company, role, and config.
            db: Active DB session.
            session_id: If provided, update this existing stub session instead of
                creating a new one. The router creates the stub upfront so users
                see 'setup' status in the list while questions are generated.

        Returns:
            SessionResponse with session ID and all generated questions.
        """
        from ..repositories.session_repository import SessionRepository
        session_repo = SessionRepository(db)

        # Optionally fetch company research for richer questions
        company_research: CompanyResearchResponse | None = None
        try:
            company_research = await self.research_company(
                request.company_name, None, db
            )
        except Exception as exc:
            logger.warning("Company research failed — proceeding without: %s", exc)

        # Generate questions
        questions = await self._question_gen.generate(
            config=request.config,
            company_name=request.company_name,
            role_title=request.role_title,
            company_research=company_research,
            jd_text=request.jd_text,
        )

        # Use the stub session created upfront by the router, or create fresh
        if session_id:
            session = await session_repo.get_session(session_id)
            if not session:
                raise ValueError(f"Stub session {session_id} not found — cannot populate questions")
        else:
            session = await session_repo.create_session(
                application_id=request.application_id,
                company_name=request.company_name,
                role_title=request.role_title,
                config=request.config.model_dump(),
            )

        # Generate model answers and persist questions
        candidate_summary = _load_candidate_summary()
        research_dict = company_research.model_dump() if company_research else {}

        db_questions = []
        for i, q in enumerate(questions):
            model_answer = await self._model_answer_gen.generate(
                question=q.text,
                category=q.category,
                difficulty=q.difficulty,
                company_name=request.company_name,
                company_research=research_dict,
                candidate_summary=candidate_summary,
            )
            db_questions.append({
                "question_num": i + 1,
                "text": q.text,
                "category": q.category,
                "difficulty": q.difficulty,
                "context": q.context,
                "model_answer": model_answer,
                "order_in_session": i + 1,
            })

        saved_questions = await session_repo.add_questions(session.id, db_questions)
        await session_repo.update_session_status(session.id, "active")
        await db.commit()

        # Map saved DB questions to QuestionPresentation
        total = len(saved_questions)
        _question_presentations = [
            QuestionPresentation(
                id=sq.id,
                text=sq.text,
                category=sq.category,
                difficulty=sq.difficulty,
                context=sq.context,
                num=sq.order_in_session,
                total=total,
            )
            for sq in saved_questions
        ]

        from ..schemas.coach import SessionQuestionRead
        cfg = session.config or {}
        return SessionResponse(
            id=session.id,
            application_id=session.application_id,
            company_name=session.company_name,
            role_title=session.role_title,
            status="active",
            overall_score=None,
            questions=[SessionQuestionRead.model_validate(sq) for sq in saved_questions],
            created_at=session.created_at,
            interview_date=cfg.get("interview_date"),
        )

    async def submit_answer(
        self,
        session_id: str,
        question_id: str,
        request: SubmitAnswerRequest,
        db: AsyncSession,
    ) -> AnswerEvaluation:
        """Submit an answer for evaluation and persist the recording.

        Args:
            session_id: ID of the interview session.
            question_id: ID of the question being answered.
            request: Answer submission with transcript and optional metrics.
            db: Active DB session.

        Returns:
            AnswerEvaluation with scores and feedback.
        """
        from ..repositories.session_repository import SessionRepository
        session_repo = SessionRepository(db)

        # Load question for context
        question = await session_repo.get_question(question_id)
        if not question or question.session_id != session_id:
            raise HTTPException(status_code=404, detail="Question not found in this session")

        # Analyse speech metrics if not provided
        speech_metrics = request.speech_metrics
        if not speech_metrics and request.transcript:
            speech_metrics = self._speech_analyser.analyse(
                request.transcript, request.duration_ms
            )

        # Validate video metrics if provided
        video_metrics = None
        if request.video_metrics:
            video_metrics = self._video_analyser.validate_metrics(
                request.video_metrics.model_dump()
            )

        # Evaluate the answer
        evaluation = await self._evaluator.evaluate(
            question=question.text,
            category=question.category,
            transcript=request.transcript,
            speech_metrics=speech_metrics,
            video_metrics=video_metrics,
            model_answer=question.model_answer,
        )

        # Fuse: LLM-as-judge enrichment of the rubric (falls back silently on failure)
        try:
            evaluation.rubric = await self._rubric_synthesiser.synthesise(
                transcript=request.transcript,
                evaluation=evaluation,
                speech_metrics=speech_metrics,
            )
        except Exception as exc:
            logger.warning("Rubric synthesis skipped: %s", exc)

        # Persist recording + evaluation
        recording_type = (
            "audio" if request.audio_uri
            else ("audio" if request.speech_metrics else "text")
        )
        await session_repo.save_recording(
            session_id=session_id,
            question_id=question_id,
            recording_type=recording_type,
            transcript=request.transcript,
            speech_metrics=speech_metrics.model_dump() if speech_metrics else None,
            video_metrics=video_metrics.model_dump() if video_metrics else None,
            evaluation_json=json.dumps(evaluation.model_dump()),
            audio_uri=request.audio_uri,
        )
        await db.commit()

        return evaluation

    async def end_session(self, session_id: str, db: AsyncSession) -> SessionFeedbackReport:
        """End a session and generate the comprehensive feedback report.

        Args:
            session_id: ID of the interview session.
            db: Active DB session.

        Returns:
            SessionFeedbackReport.
        """
        from ..repositories.session_repository import SessionRepository
        session_repo = SessionRepository(db)

        session = await session_repo.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        recordings = await session_repo.get_recordings(session_id)
        questions = await session_repo.get_questions(session_id)

        # Build question evaluation tuples
        q_map = {q.id: q for q in questions}
        question_evaluations: list[tuple[str, str, str, AnswerEvaluation]] = []
        speech_summaries: list[dict] = []

        for rec in recordings:
            if not rec.evaluation_json:
                continue
            try:
                eval_data = json.loads(rec.evaluation_json)
                eval_ = AnswerEvaluation(**eval_data)
                q = q_map.get(rec.question_id or "")
                question_evaluations.append((
                    rec.question_id or "",
                    q.text if q else "Unknown question",
                    q.category if q else "General",
                    eval_,
                ))
                if rec.speech_metrics:
                    speech_summaries.append(rec.speech_metrics)
            except Exception as exc:
                logger.warning("Failed to parse recording evaluation: %s", exc)

        # Generate report
        report = await self._feedback_gen.generate_report(
            session_id=session_id,
            role_title=session.role_title,
            company_name=session.company_name,
            question_evaluations=question_evaluations,
            speech_summaries=speech_summaries or None,
        )

        # Update session with score and summary
        await session_repo.update_session_score(
            session_id, report.overall_score, report.executive_summary
        )
        await session_repo.update_session_status(session_id, "completed")
        await db.commit()

        return report

    async def get_report(self, session_id: str, db: AsyncSession) -> SessionFeedbackReport:
        """Return a stored or regenerated feedback report for a completed session.

        Args:
            session_id: ID of the interview session.
            db: Active DB session.

        Returns:
            SessionFeedbackReport.
        """
        from ..repositories.session_repository import SessionRepository
        session_repo = SessionRepository(db)

        session = await session_repo.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if session.status not in ("completed",):
            raise HTTPException(status_code=422, detail="Session is not yet complete")

        # Regenerate from recordings
        return await self.end_session.__wrapped__(self, session_id, db)  # type: ignore[attr-defined]

    async def list_sessions(
        self, db: AsyncSession, limit: int = 20, status: str | None = None
    ) -> list[SessionListItem]:
        """List interview sessions.

        Args:
            db: Active DB session.
            limit: Max results.
            status: Optional status filter.

        Returns:
            List of SessionListItem.
        """
        from ..repositories.session_repository import SessionRepository
        session_repo = SessionRepository(db)
        return await session_repo.list_sessions(limit, status)

    async def get_session(self, session_id: str, db: AsyncSession) -> SessionResponse:
        """Get a session with all questions.

        Args:
            session_id: Session UUID.
            db: Active DB session.

        Returns:
            SessionResponse.
        """
        from ..repositories.session_repository import SessionRepository
        session_repo = SessionRepository(db)

        session = await session_repo.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        questions = await session_repo.get_questions(session_id)
        from ..schemas.coach import SessionQuestionRead
        cfg = session.config or {}
        return SessionResponse(
            id=session.id,
            application_id=session.application_id,
            company_name=session.company_name,
            role_title=session.role_title,
            status=session.status,
            overall_score=session.overall_score,
            questions=[SessionQuestionRead.model_validate(q) for q in questions],
            created_at=session.created_at,
            interview_date=cfg.get("interview_date"),
        )

    async def get_next_question(
        self, session_id: str, db: AsyncSession
    ) -> QuestionPresentation | None:
        """Get the next unanswered question in a session.

        Args:
            session_id: Session UUID.
            db: Active DB session.

        Returns:
            Next QuestionPresentation, or None if session complete.
        """
        from ..repositories.session_repository import SessionRepository
        session_repo = SessionRepository(db)

        questions = await session_repo.get_questions(session_id)
        recordings = await session_repo.get_recordings(session_id)
        answered_ids = {r.question_id for r in recordings if r.question_id}

        total = len(questions)
        all_q = [
            QuestionPresentation(
                id=q.id, text=q.text, category=q.category,
                difficulty=q.difficulty, context=q.context,
                num=q.order_in_session, total=total,
            )
            for q in questions
        ]
        return self._mock_interviewer.get_next_question(all_q, answered_ids)
