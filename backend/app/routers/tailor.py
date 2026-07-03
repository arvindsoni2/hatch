"""FastAPI router for the Tailor module — CV & cover letter generation pipeline."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas.document import DocumentListItem, GeneratedDocumentRead
from ..schemas.tailor import (
    JDAnalysisResult,
    RegenerateSectionRequest,
    TailorRequest,
)
from ..services.async_job_service import AsyncJobService
from ..services.master_cv_store import resolve_master_cv_path
from ..services.tailor_service import TailorService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tailor", tags=["tailor"])


def get_tailor_service() -> TailorService:
    """Dependency factory for TailorService (stateless, re-created per request)."""
    return TailorService()


@router.get("/templates")
async def list_templates() -> dict:
    from ..services.profile_service import load_profile_raw
    from ..services.resume_template_registry import template_payload
    try:
        tailoring = load_profile_raw().get("tailoring", {})
        design = tailoring.get("resume_design_defaults", {})
        preset = design.get("presets", {}).get(design.get("active_preset_id", "default"), {})
        if not preset:
            preset = {"template_id": tailoring.get("default_template_id", "ats_classic")}
    except Exception:
        preset = {}
    return template_payload(preset)


@router.get("/review/{application_id}")
async def get_tailoring_review(
    application_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    from ..services.tailoring_review import latest_review
    review = await latest_review(db, application_id)
    if review is None:
        return {
            "application_id": application_id,
            "available": False,
            "message": "No review data available for this generation.",
        }
    return {"available": True, **review}


@router.get("/quality/document/{document_id}")
async def get_document_quality(document_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    from sqlalchemy import desc, select
    from ..models.tailoring_review import TailoringReview
    result = await db.execute(
        select(TailoringReview).where(TailoringReview.cv_document_id == document_id)
        .order_by(desc(TailoringReview.created_at)).limit(1)
    )
    row = result.scalar_one_or_none()
    return (row.review_json.get("quality_gate", {}) if row else {})


class QualityPrecheckRequest(BaseModel):
    analysis: JDAnalysisResult
    design_settings: dict


class TemplateRecommendationRequest(BaseModel):
    analysis: JDAnalysisResult
    profile_summary: dict = Field(default_factory=dict)


@router.post("/templates/recommend")
async def recommend_resume_templates(body: TemplateRecommendationRequest) -> dict:
    import json
    from ..services.resume_template_recommender import recommend_templates

    try:
        master_cv = json.loads(resolve_master_cv_path().read_text())
    except Exception:
        master_cv = {}
    return recommend_templates(body.analysis, body.profile_summary, master_cv)


@router.post("/quality/precheck")
async def quality_precheck(body: QualityPrecheckRequest) -> dict:
    import json
    from ..services.cv_quality_gate import pre_generation_quality
    try:
        evidence = json.loads(resolve_master_cv_path().read_text())
    except Exception:
        evidence = {}
    return pre_generation_quality(body.analysis, evidence, body.design_settings.get("template_id", "ats_classic"))


class DefaultTemplateRequest(BaseModel):
    template_id: str
    design_settings: dict | None = None


@router.put("/templates/default")
async def set_default_template(body: DefaultTemplateRequest) -> dict:
    from ..services.profile_service import load_profile_raw, save_profile_raw
    from ..services.resume_template_registry import resolve_template
    template, warning = resolve_template(body.template_id)
    if warning:
        raise HTTPException(status_code=422, detail=warning)
    profile = load_profile_raw()
    tailoring = profile.setdefault("tailoring", {})
    tailoring["default_template_id"] = template["id"]
    if body.design_settings:
        from ..services.resume_design_settings import ResumeDesignSettings
        settings = ResumeDesignSettings.model_validate({**body.design_settings, "template_id": template["id"]})
        tailoring["resume_design_defaults"] = {
            "active_preset_id": "default", "presets": {"default": settings.model_dump()}
        }
    save_profile_raw(profile)
    return {"default_template_id": template["id"], "design_settings": body.design_settings}


# ---------------------------------------------------------------------------
# JD Analysis
# ---------------------------------------------------------------------------


@router.post("/analyse/{job_id}", status_code=202)
async def analyse_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    svc: TailorService = Depends(get_tailor_service),
) -> dict:
    """Kick off JD analysis for a saved job posting. Poll /api/async-jobs/{job_id} for result."""
    async_job = await AsyncJobService.create(db, "tailor_analyse")
    await db.commit()

    async def _work() -> None:
        try:
            result = await svc.analyse_job(job_id, db)
            await AsyncJobService._finish(async_job.id, result.model_dump_json(), None)
        except Exception as exc:
            await AsyncJobService._finish(async_job.id, None, str(exc))

    AsyncJobService.run(async_job.id, _work())
    return {"job_id": async_job.id, "status": "pending", "type": "tailor_analyse"}


@router.post("/analyse", status_code=202)
async def analyse_jd_text(
    job_description: str = Query(..., description="Raw JD text to analyse"),
    job_url: Optional[str] = Query(None, description="Optional URL to fetch JD from"),
    db: AsyncSession = Depends(get_db),
    svc: TailorService = Depends(get_tailor_service),
) -> dict:
    """Kick off JD analysis as a background job. Poll /api/async-jobs/{job_id} for result."""
    async_job = await AsyncJobService.create(db, "tailor_analyse")
    await db.commit()

    async def _work() -> None:
        try:
            result = await svc.analyse_jd_text(job_description, job_url)
            await AsyncJobService._finish(async_job.id, result.model_dump_json(), None)
        except Exception as exc:
            await AsyncJobService._finish(async_job.id, None, str(exc))

    AsyncJobService.run(async_job.id, _work())
    return {"job_id": async_job.id, "status": "pending", "type": "tailor_analyse"}


# ---------------------------------------------------------------------------
# Document Generation
# ---------------------------------------------------------------------------


def _require_master_cv() -> None:
    """Raise HTTP 409 if no confirmed master CV exists yet."""
    if not resolve_master_cv_path().exists():
        raise HTTPException(
            status_code=409,
            detail=(
                "No master CV found. Upload your CV in Settings → Resume "
                "before generating documents."
            ),
        )


@router.post("/generate-cv", status_code=202)
async def generate_cv(
    request: TailorRequest,
    db: AsyncSession = Depends(get_db),
    svc: TailorService = Depends(get_tailor_service),
) -> dict:
    """Kick off CV generation. Poll /api/async-jobs/{job_id} for result."""
    jd_text = request.jd_text or ""
    if not jd_text:
        raise HTTPException(status_code=422, detail="jd_text is required")
    _require_master_cv()

    async_job = await AsyncJobService.create(db, "tailor_generate_cv")
    await db.commit()

    async def _work() -> None:
        try:
            result = await svc.generate_cv(
                request.application_id,
                request.variant,
                jd_text,
                db,
                request.custom_instructions,
                request.design_settings.template_id if request.design_settings else request.template_id,
                request.design_settings.model_dump() if request.design_settings else None,
            )
            await AsyncJobService._finish(async_job.id, result.model_dump_json(), None)
        except Exception as exc:
            await AsyncJobService._finish(async_job.id, None, str(exc))

    AsyncJobService.run(async_job.id, _work())
    return {"job_id": async_job.id, "status": "pending", "type": "tailor_generate_cv"}


@router.post("/generate-cl", status_code=202)
async def generate_cover_letter(
    request: TailorRequest,
    db: AsyncSession = Depends(get_db),
    svc: TailorService = Depends(get_tailor_service),
) -> dict:
    """Kick off cover letter generation. Poll /api/async-jobs/{job_id} for result."""
    jd_text = request.jd_text or ""
    _require_master_cv()
    async_job = await AsyncJobService.create(db, "tailor_generate_cl")
    await db.commit()

    async def _work() -> None:
        try:
            result = await svc.generate_cover_letter(
                request.application_id, request.variant, jd_text, db
            )
            await AsyncJobService._finish(async_job.id, result.model_dump_json(), None)
        except Exception as exc:
            await AsyncJobService._finish(async_job.id, None, str(exc))

    AsyncJobService.run(async_job.id, _work())
    return {"job_id": async_job.id, "status": "pending", "type": "tailor_generate_cl"}


@router.post("/generate", status_code=202)
async def generate_all(
    request: TailorRequest,
    generate_variants: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    svc: TailorService = Depends(get_tailor_service),
) -> dict:
    """Kick off full pipeline (JD + CV + CL). Poll /api/async-jobs/{job_id} for result.

    When application_id is omitted, a JobPosting + Application are created
    automatically in the pipeline so documents are always tracked.
    """
    jd_text = request.jd_text or ""
    _require_master_cv()
    async_job = await AsyncJobService.create(db, "tailor_generate")
    await db.commit()

    async def _work() -> None:
        from ..database import AsyncSessionLocal  # noqa: PLC0415
        result = None
        exc_str: str | None = None
        try:
            async with AsyncSessionLocal() as job_db:
                # Hard 2-hour ceiling: with 7 concurrent jobs each taking ~3 LLM
                # calls at ~180s/call, the last job waits 6×3×180s=3240s in queue
                # before its first call starts. 7200s covers that plus generation.
                result = await asyncio.wait_for(
                    svc.generate_all(
                        application_id=request.application_id,
                        variant=request.variant,
                        jd_text=jd_text,
                        db=job_db,
                        generate_variants=generate_variants,
                        job_title=request.job_title,
                        company_name=request.company_name,
                        job_url=request.job_url,
                        custom_instructions=request.custom_instructions,
                        template_id=request.template_id,
                        design_settings=request.design_settings.model_dump() if request.design_settings else None,
                    ),
                    timeout=7200,  # 2-hour ceiling (7 jobs × 3 calls × 180s = 3780s queue wait)
                )
        except asyncio.TimeoutError:
            logger.error(
                "generate_all timed out after 2h for async job %s — "
                "LLM queue backed up with concurrent jobs",
                async_job.id,
            )
            exc_str = "Pipeline timed out after 2 hours. Too many concurrent jobs in queue — try again when other jobs are done."
        except Exception as exc:
            logger.exception("generate_all failed for async job %s: %s", async_job.id, exc)
            exc_str = str(exc)
        # Call _finish AFTER the session is fully closed to avoid SQLite write-lock deadlock
        await AsyncJobService._finish(async_job.id, result.model_dump_json() if result else None, exc_str)

    AsyncJobService.run(async_job.id, _work())
    return {"job_id": async_job.id, "status": "pending", "type": "tailor_generate"}


# ---------------------------------------------------------------------------
# SSE Stream
# ---------------------------------------------------------------------------


@router.get("/generate/stream")
async def stream_generation(
    application_id: str = Query(...),
    variant: str = Query("A"),
    jd_text: str = Query(...),
    db: AsyncSession = Depends(get_db),
    svc: TailorService = Depends(get_tailor_service),
) -> StreamingResponse:
    """Stream pipeline progress as Server-Sent Events.

    Yields events: analysing_jd → skill_match → tailoring_cv → scoring_ats →
                   improving_cv → generating_cl → building_docx → complete
    """
    return StreamingResponse(
        svc.stream_progress(application_id, variant, jd_text, db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Regeneration
# ---------------------------------------------------------------------------


@router.post("/regenerate-section", response_model=dict)
async def regenerate_section(
    request: RegenerateSectionRequest,
    db: AsyncSession = Depends(get_db),
    svc: TailorService = Depends(get_tailor_service),
) -> dict:
    """Regenerate a specific section of a cover letter paragraph."""
    from ..repositories.document_repository import DocumentRepository

    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(request.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.document_type != "cover_letter":
        raise HTTPException(status_code=422, detail="regenerate-section only supports cover_letter documents")

    raise HTTPException(
        status_code=501,
        detail="Regenerate section requires the stored CoverLetterResult — store it in jd_analysis_snapshot first"
    )


# ---------------------------------------------------------------------------
# History & Downloads
# ---------------------------------------------------------------------------


@router.get("/history/{application_id}", response_model=list[DocumentListItem])
async def get_document_history(
    application_id: str,
    doc_type: Optional[str] = Query(None, description="Filter: 'cv' or 'cover_letter'"),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentListItem]:
    """List all generated documents for an application."""
    from ..repositories.document_repository import DocumentRepository
    doc_repo = DocumentRepository(db)
    return await doc_repo.list_by_application(application_id, doc_type)


@router.get("/document/{document_id}", response_model=GeneratedDocumentRead)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
) -> GeneratedDocumentRead:
    """Get metadata for a generated document."""
    from ..repositories.document_repository import DocumentRepository
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/document/{document_id}/download")
async def download_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    svc: TailorService = Depends(get_tailor_service),
) -> FileResponse:
    """Download a generated .docx document."""
    file_path, filename = await svc.download_document(document_id, db)
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# ---------------------------------------------------------------------------
# ATS Scoring
# ---------------------------------------------------------------------------


@router.get("/ats-score/{document_id}")
async def get_ats_score(
    document_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the stored ATS score details for a generated CV document."""
    import json
    from ..repositories.document_repository import DocumentRepository
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.ats_details:
        return {"ats_score": doc.ats_score, "details": None}
    return {"ats_score": doc.ats_score, "details": json.loads(doc.ats_details)}


@router.post("/ats-optimise/{document_id}")
async def ats_optimise(
    document_id: str,
    jd_text: str = Query(...),
    db: AsyncSession = Depends(get_db),
    svc: TailorService = Depends(get_tailor_service),
) -> dict:
    """Re-run ATS scoring on an existing document and return updated suggestions."""
    import json
    from ..repositories.document_repository import DocumentRepository
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    analysis = await svc._jd_analyser.analyse(jd_text)
    if doc.jd_analysis_snapshot:
        from ..schemas.tailor import JDAnalysisResult
        try:
            analysis = JDAnalysisResult(**json.loads(doc.jd_analysis_snapshot))
        except Exception:
            pass

    suggestions = svc._ats_optimiser.suggest_improvements(
        await svc._ats_optimiser.score("", analysis)
    )
    return {"suggestions": suggestions}
