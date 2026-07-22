"""FastAPI router for the Coach module — mock interview practice sessions."""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas.coach import (
    CompanyResearchResponse,
    CreateSessionRequest,
    SessionConfig,
    PlanFollowUpResponse,
    ProgressTrendItem,
    QuestionPresentation,
    SessionFeedbackReport,
    SessionListItem,
    SessionResponse,
    SpeechMetrics,
    SubmitAnswerRequest,
)
from ..services.async_job_service import AsyncJobService
from ..services.coach_session_queue import queue_coach_session
from ..services.coach_service import CoachService
from ..services.coach_contracts import CoachConflictError, failed_answer_payload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/coach", tags=["coach"])

# Strict allowlist: server-generated UUIDs and slug IDs only (no path separators)
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# Map content-type → file extension (never trust the user-supplied filename)
_AUDIO_CT_TO_EXT: dict[str, str] = {
    "audio/webm": ".webm",
    "audio/wav": ".wav",
    "audio/wave": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
}


def _require_safe_id(value: str, field: str) -> None:
    if not _SAFE_ID_RE.match(value):
        raise HTTPException(status_code=400, detail=f"Invalid {field}: must be alphanumeric/dash/underscore only")


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


@router.post("/sessions", status_code=202)
async def create_session(
    request: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
    svc: CoachService = Depends(get_coach_service),
) -> dict:
    """Kick off session creation (question generation). Poll /api/async-jobs/{job_id}.

    A stub session record (status='setup') is written to the DB immediately so the
    coach session list shows it as 'Generating…' while the async job runs.  The
    async job uses its own DB session (not the request session) to avoid accessing
    a closed connection after the HTTP response has been sent.
    """
    return await queue_coach_session(request, db, svc)


@router.get("/sessions", response_model=list[SessionListItem])
async def list_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(
        None,
        description="Filter by status: setup|active|completed|failed|abandoned",
    ),
    db: AsyncSession = Depends(get_db),
    svc: CoachService = Depends(get_coach_service),
) -> list[SessionListItem]:
    """List interview sessions, newest first.

    Abandoned is the user-deleted state, so it is omitted from the default
    collection. Callers may still request it explicitly for diagnostics.
    """
    return await svc.list_sessions(
        db,
        limit=limit,
        status=status,
        exclude_abandoned=status is None,
    )


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


@router.post("/sessions/{session_id}/retry", status_code=202)
async def retry_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    svc: CoachService = Depends(get_coach_service),
) -> dict:
    """Retry a stale or failed Coach session using the original session metadata."""
    from ..repositories.session_repository import SessionRepository

    repo = SessionRepository(db)
    session = await repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    config = dict(session.config or {})
    session_config_keys = set(SessionConfig.model_fields.keys())
    session_config = SessionConfig(
        **{key: value for key, value in config.items() if key in session_config_keys}
    )
    interview_date = config.get("interview_date")
    jd_text = config.get("jd_text")

    if session.status != "abandoned":
        await repo.update_session_status(session_id, "abandoned")
        await db.flush()

    return await queue_coach_session(
        CreateSessionRequest(
            application_id=session.application_id,
            company_name=session.company_name,
            role_title=session.role_title,
            jd_text=jd_text if isinstance(jd_text, str) else None,
            interview_date=interview_date if isinstance(interview_date, str) else None,
            config=session_config,
        ),
        db,
        svc,
    )


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
    from ..services.coach_reconciliation import reconcile_session

    await reconcile_session(db, session_id)
    repo = SessionRepository(db)
    try:
        await repo.record_skip(session_id=session_id, question_id=question_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Question not found in this session")
    except CoachConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    await db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Answer submission
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/submit-answer", status_code=202)
async def submit_answer(
    session_id: str,
    question_id: str = Query(...),
    request: SubmitAnswerRequest = ...,
    db: AsyncSession = Depends(get_db),
    svc: CoachService = Depends(get_coach_service),
) -> dict:
    """Kick off answer evaluation. Poll /api/async-jobs/{job_id} for scores + feedback."""
    from ..repositories.session_repository import SessionRepository
    from ..services.coach_reconciliation import reconcile_session

    await reconcile_session(db, session_id)
    async_job = await AsyncJobService.create(db, "submit_answer")
    try:
        recording = await SessionRepository(db).reserve_answer_attempt(
            session_id=session_id,
            question_id=question_id,
            async_job_id=async_job.id,
            recording_type="text",
            transcript=request.transcript,
        )
        await db.commit()
    except LookupError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CoachConflictError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    request_data = request.model_dump(mode="json")
    recording_id = recording.id
    job_id = async_job.id

    async def _work() -> None:
        from ..database import AsyncSessionLocal

        async with AsyncSessionLocal() as job_db:
            try:
                reconstructed = SubmitAnswerRequest.model_validate(request_data)
                result = await CoachService().submit_answer(
                    session_id,
                    question_id,
                    reconstructed,
                    job_db,
                    recording_id=recording_id,
                    async_job_id=job_id,
                )
                await AsyncJobService._finish(
                    job_id, result.model_dump_json(), None, db=job_db
                )
            except Exception as exc:
                logger.error("submit_answer job %s failed: %s", job_id, exc)
                await SessionRepository(job_db).finalize_answer_attempt(
                    recording_id,
                    job_id,
                    evaluation_state="failed",
                    evaluation_json=json.dumps(failed_answer_payload()),
                )
                await job_db.commit()
                await AsyncJobService._finish(job_id, None, str(exc), db=job_db)

    AsyncJobService.run(job_id, _work())
    return {"job_id": job_id, "status": "pending", "type": "submit_answer"}


_MAX_AUDIO_BYTES = 50 * 1024 * 1024  # 50 MB


@router.post("/sessions/{session_id}/submit-audio", status_code=202)
async def submit_audio(
    session_id: str,
    question_id: str = Form(...),
    audio: UploadFile = File(...),
    face_summary: Optional[str] = Form(default=None),  # JSON-encoded FaceSummary (Phase D)
    db: AsyncSession = Depends(get_db),
    svc: CoachService = Depends(get_coach_service),
) -> dict:
    """Upload an audio recording for a question. Returns 202 + job_id.

    The async job transcribes the audio with faster-whisper, computes delivery
    metrics, evaluates the answer, and saves a recording with audio_uri set.
    Poll /api/async-jobs/{job_id} for the AnswerEvaluation result.
    """
    _require_safe_id(session_id, "session_id")
    _require_safe_id(question_id, "question_id")

    ct = (audio.content_type or "").split(";")[0].strip().lower()
    if not ct.startswith("audio/"):
        raise HTTPException(
            status_code=400,
            detail=f"Audio files only. Got content-type: {ct!r}",
        )

    audio_bytes = await audio.read()
    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file exceeds 50 MB limit")

    # Parse face_summary JSON if provided (Phase D)
    face_summary_dict: dict | None = None
    if face_summary:
        import json as _json  # noqa: PLC0415
        try:
            face_summary_dict = _json.loads(face_summary)
        except Exception:
            logger.warning("submit_audio: could not parse face_summary JSON — ignoring")

    from ..repositories.session_repository import SessionRepository
    from ..services.coach_reconciliation import reconcile_session

    await reconcile_session(db, session_id)
    async_job = await AsyncJobService.create(db, "submit_audio")
    job_id = async_job.id
    suffix = _AUDIO_CT_TO_EXT.get(ct, ".audio")
    recordings_dir = Path(os.getenv("DATA_DIR", "./data")) / "recordings" / session_id
    recordings_dir.mkdir(parents=True, exist_ok=True)
    audio_path = recordings_dir / f"{question_id}-{job_id}{suffix}"
    resolved = audio_path.resolve()
    if not resolved.is_relative_to(recordings_dir.resolve()):
        await db.rollback()
        raise HTTPException(status_code=400, detail="Invalid audio path")
    audio_path_str = str(audio_path)
    try:
        recording = await SessionRepository(db).reserve_answer_attempt(
            session_id=session_id,
            question_id=question_id,
            async_job_id=job_id,
            recording_type="audio",
            transcript=None,
            audio_uri=audio_path_str,
        )
        audio_path.write_bytes(audio_bytes)
        await db.commit()
    except LookupError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CoachConflictError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    recording_id = recording.id

    async def _work() -> None:
        from ..database import AsyncSessionLocal  # noqa: PLC0415
        async with AsyncSessionLocal() as job_db:
            try:
                from ..agents.tools.perception_factory import get_transcriber  # noqa: PLC0415
                from ..agents.tools.profile_loader import load_profile  # noqa: PLC0415
                from ..services.locale_service import get_coach_fillers  # noqa: PLC0415
                from ..services.speech_analyser import SpeechAnalyserService  # noqa: PLC0415

                transcriber = get_transcriber()
                result = transcriber.transcribe(audio_path_str)

                try:
                    locale_id = load_profile().locale
                    fillers: list[str] | None = get_coach_fillers(locale_id)
                except Exception:
                    fillers = None

                analyser = SpeechAnalyserService()
                words_dicts = [
                    {"w": w.w, "start": w.start, "end": w.end}
                    for w in result.words
                ]
                speech_metrics: SpeechMetrics = analyser.analyse_from_timestamps(
                    result.text, words_dicts, locale_fillers=fillers
                )

                from ..schemas.coach import VideoMetrics  # noqa: PLC0415
                video_metrics_obj: VideoMetrics | None = None
                if face_summary_dict:
                    video_metrics_obj = VideoMetrics(
                        eye_contact_pct=face_summary_dict.get("eye_contact_pct", 0.0) * 100,
                        head_stability=min(1.0, face_summary_dict.get("head_stability", 0.0)),
                        expression="neutral",
                        gesture_freq=0.0,
                    )

                request_data = {
                    "transcript": result.text,
                    "speech_metrics": speech_metrics,
                    "video_metrics": video_metrics_obj,
                    "duration_ms": speech_metrics.duration_ms,
                    "audio_uri": audio_path_str,
                }
                req = (
                    SubmitAnswerRequest(**request_data)
                    if result.text.strip()
                    else SubmitAnswerRequest.model_construct(**request_data)
                )
                evaluation = await CoachService().submit_answer(
                    session_id,
                    question_id,
                    req,
                    job_db,
                    recording_id=recording_id,
                    async_job_id=job_id,
                )
                await AsyncJobService._finish(
                    job_id, evaluation.model_dump_json(), None, db=job_db
                )
            except Exception as exc:
                logger.error("submit_audio job %s failed: %s", job_id, exc)
                await SessionRepository(job_db).finalize_answer_attempt(
                    recording_id,
                    job_id,
                    evaluation_state="failed",
                    evaluation_json=json.dumps(failed_answer_payload()),
                )
                await job_db.commit()
                await AsyncJobService._finish(job_id, None, str(exc), db=job_db)

    AsyncJobService.run(job_id, _work())
    return {"job_id": job_id, "status": "pending", "type": "submit_audio"}


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/end", status_code=202)
async def end_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    svc: CoachService = Depends(get_coach_service),
) -> dict:
    """Kick off feedback report generation. Poll /api/async-jobs/{job_id} for report."""
    from ..repositories.session_repository import SessionRepository
    from ..services.coach_contracts import CoachDiagnostic
    from ..services.coach_reconciliation import reconcile_session

    await reconcile_session(db, session_id)
    repository = SessionRepository(db)
    session = await repository.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.report_state in {"completed", "fallback"} and session.report_json:
        return JSONResponse(status_code=200, content=session.report_json)
    if session.report_state == "building" and session.report_job_id:
        return {
            "job_id": session.report_job_id,
            "status": "pending",
            "type": "end_session",
            "reused": True,
        }

    async_job = await AsyncJobService.create(db, "end_session")
    claimed = await repository.claim_report(
        session_id, async_job.id, session.activity_version
    )
    if not claimed:
        await db.rollback()
        session = await repository.get_session(session_id)
        recordings = await repository.get_recordings(session_id)
        if any(recording.evaluation_state == "pending" for recording in recordings):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "coach_answers_processing",
                    "message": "Answer evaluations are still processing.",
                },
            )
        if session and session.report_state == "building" and session.report_job_id:
            return {
                "job_id": session.report_job_id,
                "status": "pending",
                "type": "end_session",
                "reused": True,
            }
        if session and session.report_state in {"completed", "fallback"} and session.report_json:
            return JSONResponse(status_code=200, content=session.report_json)
        raise HTTPException(
            status_code=409,
            detail={"code": "coach_session_closed", "message": "Session cannot be ended."},
        )
    await db.commit()

    job_id = async_job.id

    async def _work() -> None:
        from ..database import AsyncSessionLocal

        async with AsyncSessionLocal() as job_db:
            try:
                result = await CoachService().end_session(
                    session_id, job_db, report_job_id=job_id
                )
                await AsyncJobService._finish(
                    job_id, result.model_dump_json(), None, db=job_db
                )
            except Exception as exc:
                logger.error("end_session job %s failed: %s", job_id, exc)
                diagnostic = CoachDiagnostic(
                    stage="session_report",
                    outcome="failed",
                    execution_mode="deterministic",
                    attempt_count=0,
                    repair_count=0,
                    gate_codes=["coach_async_job_failed"],
                    duration_ms=0,
                )
                await SessionRepository(job_db).fail_report_claim(
                    session_id,
                    job_id,
                    diagnostic.model_dump(mode="json"),
                )
                await job_db.commit()
                await AsyncJobService._finish(job_id, None, str(exc), db=job_db)

    AsyncJobService.run(job_id, _work())
    return {"job_id": job_id, "status": "pending", "type": "end_session"}


@router.get("/sessions/{session_id}/report", response_model=SessionFeedbackReport)
async def get_session_report(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    svc: CoachService = Depends(get_coach_service),
) -> SessionFeedbackReport:
    """Return the feedback report for a completed session."""
    from ..services.coach_reconciliation import reconcile_session

    await reconcile_session(db, session_id)
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
            started_at=r.started_at,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Phase C — Follow-up sessions + progress trend
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/plan-followup", response_model=PlanFollowUpResponse)
async def plan_followup_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    svc: CoachService = Depends(get_coach_service),
) -> PlanFollowUpResponse:
    """Plan a follow-up session targeting the weakest rubric dimensions.

    Creates a new session linked to this one via parent_session_id, with
    focus_areas set to the 1-2 lowest-scoring rubric dimensions.
    """
    return await svc.plan_followup_session(session_id, db)


@router.get("/progress/{session_id}/trend", response_model=list[ProgressTrendItem])
async def get_progress_trend(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[ProgressTrendItem]:
    """Return per-session progress trend for the session chain containing session_id."""
    from ..repositories.session_repository import SessionRepository
    repo = SessionRepository(db)
    trend_data = await repo.get_progress_trend(session_id)
    return [
        ProgressTrendItem(
            session_id=item["session_id"],
            created_at=item["created_at"],
            overall_score=item["overall_score"],
            rubric_scores=item["rubric_scores"],
            focus_areas=item["focus_areas"],
        )
        for item in trend_data
    ]


# ---------------------------------------------------------------------------
# Phase D — Capabilities endpoint
# ---------------------------------------------------------------------------


@router.get("/capabilities")
async def get_capabilities() -> dict:
    """Return which perception capabilities are enabled per profile.yaml."""
    try:
        from ..agents.tools.profile_loader import load_profile  # noqa: PLC0415
        profile = load_profile()
        return {
            "face_analysis": profile.perception.face.enabled,
            "tts": profile.perception.tts.provider != "none",
        }
    except Exception:
        return {"face_analysis": False, "tts": False}


# ---------------------------------------------------------------------------
# Phase E — TTS question synthesis
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/tts-question")
async def synthesise_question(
    session_id: str,
    question_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Return WAV audio of the question text via configured TTS provider.

    Returns 503 if TTS is disabled or the piper binary is not available.
    """
    from .._exceptions import PerceptionNotAvailableError  # noqa: PLC0415
    from ..agents.tools.perception_factory import get_tts  # noqa: PLC0415
    from ..repositories.session_repository import SessionRepository  # noqa: PLC0415

    try:
        tts = get_tts()
    except PerceptionNotAvailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    repo = SessionRepository(db)
    q = await repo.get_question(question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    try:
        audio_bytes = await tts.synthesise(q.text)
    except PerceptionNotAvailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as exc:
        logger.error("TTS synthesis failed: %s", exc)
        raise HTTPException(status_code=500, detail="TTS synthesis failed") from exc

    return Response(content=audio_bytes, media_type="audio/wav")
