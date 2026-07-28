"""Database access layer for Coach interview sessions, questions, and recordings."""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.coach_session import InterviewSession, SessionQuestion, SessionRecording
from ..schemas.coach import SessionListItem
from ..schemas.coach_conversation import project_retention_summary
from ..services.coach_contracts import CoachConflictError, merge_stage_diagnostic

logger = logging.getLogger(__name__)





class SessionRepository:
    """All database operations for interview sessions, questions, and recordings."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ──────────────────────── Sessions ────────────────────────

    async def create_session(
        self,
        company_name: str,
        role_title: str,
        config: dict,
        application_id: str | None = None,
    ) -> InterviewSession:
        """Create a new interview session record.

        Args:
            company_name: Name of the company being interviewed for.
            role_title: Job title / role being practised.
            config: Session configuration dict (question_count, categories, etc.).
            application_id: Optional FK to an application record.

        Returns:
            Persisted InterviewSession ORM object.
        """
        session = InterviewSession(
            application_id=application_id,
            company_name=company_name,
            role_title=role_title,
            config=config,
            status="setup",
            started_at=datetime.utcnow(),
        )
        self._session.add(session)
        await self._session.flush()
        await self._session.refresh(session)
        return session

    async def get_session(self, session_id: str) -> InterviewSession | None:
        """Fetch an interview session by its primary key.

        Args:
            session_id: UUID of the session.

        Returns:
            InterviewSession ORM object, or None if not found.
        """
        result = await self._session.execute(
            select(InterviewSession).where(InterviewSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def list_sessions(
        self,
        limit: int = 20,
        status: str | None = None,
        *,
        exclude_abandoned: bool = False,
    ) -> list[SessionListItem]:
        """List interview sessions, newest first.

        Args:
            limit: Maximum number of results.
            status: Optional status filter (setup|active|completed|failed|abandoned).
            exclude_abandoned: Hide sessions explicitly removed by the user.

        Returns:
            List of SessionListItem Pydantic schemas.
        """
        query = select(InterviewSession).order_by(InterviewSession.created_at.desc()).limit(limit)
        if status:
            query = query.where(InterviewSession.status == status)
        elif exclude_abandoned:
            query = query.where(InterviewSession.status != "abandoned")
        result = await self._session.execute(query)
        rows = result.scalars().all()
        return [
            SessionListItem(
                id=r.id,
                company_name=r.company_name,
                role_title=r.role_title,
                status=r.status,
                overall_score=r.overall_score,
                created_at=r.created_at,
                started_at=r.started_at,
                experience_version=r.experience_version,
                conversation_state=r.conversation_state,
                retention_summary=project_retention_summary(r.retention_policy_json),
            )
            for r in rows
        ]

    async def update_session_status(self, session_id: str, status: str) -> None:
        """Update the status of an interview session.

        Args:
            session_id: UUID of the session.
            status: New status string (setup|active|completed|abandoned).
        """
        extra: dict = {}
        if status == "completed":
            extra["completed_at"] = datetime.utcnow()
        await self._session.execute(
            update(InterviewSession)
            .where(InterviewSession.id == session_id)
            .values(status=status, **extra)
        )

    async def update_session_score(
        self, session_id: str, overall_score: float | None, feedback_summary: str
    ) -> None:
        """Persist the overall score and executive feedback summary for a session.

        Args:
            session_id: UUID of the session.
            overall_score: Aggregated score (0-10).
            feedback_summary: Executive summary text.
        """
        await self._session.execute(
            update(InterviewSession)
            .where(InterviewSession.id == session_id)
            .values(overall_score=overall_score, feedback_summary=feedback_summary)
        )

    async def update_stage_diagnostics(
        self,
        session_id: str,
        stage: str,
        value: dict,
    ) -> None:
        """Merge one Coach stage diagnostic without dropping other stages."""
        session = await self.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")
        merged = merge_stage_diagnostic(session.diagnostics, stage, value)
        await self._session.execute(
            update(InterviewSession)
            .where(InterviewSession.id == session_id)
            .values(diagnostics=merged)
        )

    async def claim_report(
        self,
        session_id: str,
        job_id: str,
        expected_activity_version: int,
    ) -> bool:
        """Atomically claim report generation when the session is stable and open."""
        pending = exists().where(
            SessionRecording.session_id == session_id,
            SessionRecording.evaluation_state == "pending",
        )
        result = await self._session.execute(
            update(InterviewSession)
            .where(
                InterviewSession.id == session_id,
                InterviewSession.status == "active",
                InterviewSession.report_state.in_(("not_started", "failed")),
                InterviewSession.activity_version == expected_activity_version,
                ~pending,
            )
            .values(
                report_state="building",
                report_job_id=job_id,
                report_started_at=datetime.utcnow(),
            )
        )
        return result.rowcount == 1

    async def finalize_report_claim(
        self,
        session_id: str,
        job_id: str,
        *,
        report_json: dict,
        rubric: dict,
        overall_score: float | None,
        feedback_summary: str,
        report_state: str,
        report_diagnostic: dict,
        aggregation_diagnostic: dict,
    ) -> bool:
        """Persist a complete immutable snapshot iff this worker owns the claim."""
        session = await self.get_session(session_id)
        if session is None:
            return False
        diagnostics = merge_stage_diagnostic(
            session.diagnostics,
            "session_rubric_aggregation",
            {"final": aggregation_diagnostic},
        )
        diagnostics = merge_stage_diagnostic(
            diagnostics,
            "session_report",
            {"final": report_diagnostic},
        )
        result = await self._session.execute(
            update(InterviewSession)
            .where(
                InterviewSession.id == session_id,
                InterviewSession.report_job_id == job_id,
                InterviewSession.report_state == "building",
            )
            .values(
                report_json=report_json,
                rubric=rubric,
                overall_score=overall_score,
                feedback_summary=feedback_summary,
                diagnostics=diagnostics,
                report_state=report_state,
                status="completed",
                completed_at=datetime.utcnow(),
                report_started_at=None,
            )
        )
        return result.rowcount == 1

    async def fail_report_claim(
        self,
        session_id: str,
        job_id: str,
        diagnostic: dict,
        reason_code: str | None = None,
    ) -> bool:
        """Return an owned building report claim to a retryable failed state."""
        session = await self.get_session(session_id)
        if session is None:
            return False
        stage_value = {"final": diagnostic}
        if reason_code:
            stage_value["reason_code"] = reason_code
        diagnostics = merge_stage_diagnostic(
            session.diagnostics, "session_report", stage_value
        )
        result = await self._session.execute(
            update(InterviewSession)
            .where(
                InterviewSession.id == session_id,
                InterviewSession.report_job_id == job_id,
                InterviewSession.report_state == "building",
            )
            .values(
                report_state="failed",
                status="active",
                report_started_at=None,
                diagnostics=diagnostics,
            )
        )
        return result.rowcount == 1

    # ──────────────────────── Questions ────────────────────────

    async def add_questions(
        self, session_id: str, questions: list[dict]
    ) -> list[SessionQuestion]:
        """Bulk-insert questions for a session.

        Args:
            session_id: UUID of the parent session.
            questions: List of dicts with keys: question_num, text, category,
                difficulty, context, model_answer, order_in_session.

        Returns:
            List of persisted SessionQuestion ORM objects.
        """
        db_questions = []
        for q in questions:
            sq = SessionQuestion(
                session_id=session_id,
                question_num=q["question_num"],
                text=q["text"],
                category=q["category"],
                difficulty=q.get("difficulty", "medium"),
                context=q.get("context"),
                model_answer=q.get("model_answer"),
                requirement_id=q.get("requirement_id"),
                model_answer_diagnostics=q.get("model_answer_diagnostics"),
                order_in_session=q["order_in_session"],
            )
            self._session.add(sq)
            db_questions.append(sq)

        await self._session.flush()
        for sq in db_questions:
            await self._session.refresh(sq)
        return db_questions

    async def get_questions(self, session_id: str) -> list[SessionQuestion]:
        """Fetch all questions for a session, ordered by order_in_session.

        Args:
            session_id: UUID of the session.

        Returns:
            Ordered list of SessionQuestion ORM objects.
        """
        result = await self._session.execute(
            select(SessionQuestion)
            .where(SessionQuestion.session_id == session_id)
            .order_by(SessionQuestion.order_in_session)
        )
        return list(result.scalars().all())

    async def get_question(self, question_id: str) -> SessionQuestion | None:
        """Fetch a single question by its primary key.

        Args:
            question_id: UUID of the question.

        Returns:
            SessionQuestion ORM object, or None if not found.
        """
        result = await self._session.execute(
            select(SessionQuestion).where(SessionQuestion.id == question_id)
        )
        return result.scalar_one_or_none()

    # ──────────────────────── Recordings ────────────────────────

    async def save_recording(
        self,
        session_id: str,
        question_id: str,
        recording_type: str,
        transcript: str | None,
        speech_metrics: dict | None,
        video_metrics: dict | None,
        evaluation_json: str | None,
        audio_uri: str | None = None,
        video_uri: str | None = None,
        evaluation_state: str | None = None,
        async_job_id: str | None = None,
    ) -> SessionRecording:
        """Persist a recording (transcript + optional media URIs + evaluation).

        Args:
            session_id: UUID of the parent session.
            question_id: UUID of the question being answered.
            recording_type: 'audio', 'video', or 'text'.
            transcript: Answer transcript text.
            speech_metrics: Dict of speech analysis metrics.
            video_metrics: Dict of video analysis metrics.
            evaluation_json: JSON-serialised AnswerEvaluation.
            audio_uri: Optional path/URL to audio file.
            video_uri: Optional path/URL to video file.

        Returns:
            Persisted SessionRecording ORM object.
        """
        recording = SessionRecording(
            session_id=session_id,
            question_id=question_id,
            recording_type=recording_type,
            transcript=transcript,
            audio_uri=audio_uri,
            video_uri=video_uri,
            speech_metrics=speech_metrics,
            video_metrics=video_metrics,
            evaluation_json=evaluation_json,
            evaluation_state=evaluation_state,
            async_job_id=async_job_id,
        )
        self._session.add(recording)
        await self._session.flush()
        await self._session.refresh(recording)
        return recording

    async def reserve_answer_attempt(
        self,
        *,
        session_id: str,
        question_id: str,
        async_job_id: str,
        recording_type: str,
        transcript: str | None,
        audio_uri: str | None = None,
    ) -> SessionRecording:
        """Atomically reserve one immutable pending answer attempt."""
        question = await self.get_question(question_id)
        if question is None or question.session_id != session_id:
            raise LookupError("Question not found in this session")
        session = await self.get_session(session_id)
        if session is None:
            raise LookupError("Session not found")

        claimed = await self._session.execute(
            update(InterviewSession)
            .where(
                InterviewSession.id == session_id,
                InterviewSession.status == "active",
                InterviewSession.report_state.in_(("not_started", "failed")),
            )
            .values(activity_version=InterviewSession.activity_version + 1)
        )
        if claimed.rowcount != 1:
            raise CoachConflictError(
                "coach_session_closed",
                "This Coach session no longer accepts answers.",
            )

        recording = SessionRecording(
            session_id=session_id,
            question_id=question_id,
            recording_type=recording_type,
            transcript=transcript,
            audio_uri=audio_uri,
            evaluation_state="pending",
            async_job_id=async_job_id,
        )
        self._session.add(recording)
        await self._session.flush()
        await self._session.refresh(recording)
        return recording

    async def record_skip(self, *, session_id: str, question_id: str) -> SessionRecording:
        """Create a terminal explicit skip under the same session guard."""
        question = await self.get_question(question_id)
        if question is None or question.session_id != session_id:
            raise LookupError("Question not found in this session")
        session = await self.get_session(session_id)
        if session is None:
            raise LookupError("Session not found")
        claimed = await self._session.execute(
            update(InterviewSession)
            .where(
                InterviewSession.id == session_id,
                InterviewSession.status == "active",
                InterviewSession.report_state.in_(("not_started", "failed")),
            )
            .values(activity_version=InterviewSession.activity_version + 1)
        )
        if claimed.rowcount != 1:
            raise CoachConflictError(
                "coach_session_closed",
                "This Coach session no longer accepts skipped answers.",
            )
        recording = SessionRecording(
            session_id=session_id,
            question_id=question_id,
            recording_type="text",
            transcript="[SKIPPED]",
            evaluation_json=None,
            evaluation_state="skipped",
            async_job_id=None,
        )
        self._session.add(recording)
        await self._session.flush()
        await self._session.refresh(recording)
        return recording

    async def finalize_answer_attempt(
        self,
        recording_id: str,
        async_job_id: str,
        *,
        evaluation_state: str,
        evaluation_json: str | None,
        transcript: str | None = None,
        speech_metrics: dict | None = None,
        video_metrics: dict | None = None,
        audio_uri: str | None = None,
    ) -> bool:
        """Persist all answer output iff the immutable pending claim still owns it."""
        values: dict = {
            "evaluation_state": evaluation_state,
            "evaluation_json": evaluation_json,
        }
        if transcript is not None:
            values["transcript"] = transcript
        if speech_metrics is not None:
            values["speech_metrics"] = speech_metrics
        if video_metrics is not None:
            values["video_metrics"] = video_metrics
        if audio_uri is not None:
            values["audio_uri"] = audio_uri
        result = await self._session.execute(
            update(SessionRecording)
            .where(
                SessionRecording.id == recording_id,
                SessionRecording.async_job_id == async_job_id,
                SessionRecording.evaluation_state == "pending",
            )
            .values(**values)
        )
        return result.rowcount == 1

    async def get_recordings(self, session_id: str) -> list[SessionRecording]:
        """Fetch all recordings for a session, oldest first.

        Args:
            session_id: UUID of the session.

        Returns:
            List of SessionRecording ORM objects.
        """
        result = await self._session.execute(
            select(SessionRecording)
            .where(SessionRecording.session_id == session_id)
            .order_by(SessionRecording.created_at)
        )
        return list(result.scalars().all())

    # ──────────────────────── Phase C: Session chains ────────────────────────

    async def update_session_phase_c(
        self,
        session_id: str,
        coach_mode: str | None = None,
        rubric: dict | None = None,
        signals: dict | None = None,
        focus_areas: list | None = None,
    ) -> None:
        """Update Phase C columns on a session.

        Args:
            session_id: UUID of the session.
            coach_mode: Recording mode (text|voice|video).
            rubric: Serialised SessionRubric dict.
            signals: Supplementary signal data dict.
            focus_areas: List of dimension names to focus on.
        """
        values: dict = {}
        if coach_mode is not None:
            values["coach_mode"] = coach_mode
        if rubric is not None:
            values["rubric"] = rubric
        if signals is not None:
            values["signals"] = signals
        if focus_areas is not None:
            values["focus_areas"] = focus_areas
        if not values:
            return
        await self._session.execute(
            update(InterviewSession)
            .where(InterviewSession.id == session_id)
            .values(**values)
        )

    async def get_session_chain(self, session_id: str) -> list[InterviewSession]:
        """Return this session + all ancestors/descendants in the chain, oldest first.

        Traverses upward to find the root session, then collects all descendants
        in creation order.

        Args:
            session_id: UUID of any session in the chain.

        Returns:
            Ordered list of InterviewSession ORM objects (oldest first).
        """
        # Load the starting session
        result = await self._session.execute(
            select(InterviewSession).where(InterviewSession.id == session_id)
        )
        current = result.scalar_one_or_none()
        if not current:
            return []

        # Walk up to the root
        root = current
        visited: set[str] = {current.id}
        while root.parent_session_id and root.parent_session_id not in visited:
            visited.add(root.parent_session_id)
            r2 = await self._session.execute(
                select(InterviewSession).where(InterviewSession.id == root.parent_session_id)
            )
            parent = r2.scalar_one_or_none()
            if not parent:
                break
            root = parent

        # BFS/DFS from root to collect all descendants
        chain: list[InterviewSession] = []
        queue = [root]
        seen: set[str] = set()
        while queue:
            node = queue.pop(0)
            if node.id in seen:
                continue
            seen.add(node.id)
            chain.append(node)
            # Load children
            children_result = await self._session.execute(
                select(InterviewSession).where(
                    InterviewSession.parent_session_id == node.id
                ).order_by(InterviewSession.created_at)
            )
            children = list(children_result.scalars().all())
            queue.extend(children)

        # Sort by created_at to ensure oldest first
        chain.sort(key=lambda s: s.created_at)
        return chain

    async def get_progress_trend(self, session_id: str) -> list[dict]:
        """Return per-skill scores across the session chain.

        Args:
            session_id: UUID of any session in the chain.

        Returns:
            List of dicts with session_id, created_at, overall_score,
            rubric_scores, and focus_areas for each session in the chain.
        """
        chain = await self.get_session_chain(session_id)
        trend = []
        for s in chain:
            rubric_scores: dict[str, int] = {}
            if s.rubric and isinstance(s.rubric, dict):
                dims = s.rubric.get("dimensions", {})
                if isinstance(dims, dict):
                    for dim_name, dim_data in dims.items():
                        if isinstance(dim_data, dict):
                            rubric_scores[dim_name] = dim_data.get("score", 0)
            trend.append({
                "session_id": s.id,
                "created_at": s.created_at,
                "overall_score": s.overall_score,
                "rubric_scores": rubric_scores,
                "focus_areas": s.focus_areas or [],
            })
        return trend
