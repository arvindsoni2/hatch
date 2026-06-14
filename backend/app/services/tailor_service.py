"""Tailor Service — orchestrates the full 3-stage Claude pipeline for CV and cover letter generation."""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.document_repository import DocumentRepository
from ..schemas.document import GeneratedDocumentRead
from ..schemas.tailor import (
    ATSScoreResult,
    JDAnalysisResponse,
    TailorResultBundle,
)
from .ats_optimiser import ATSOptimiser
from .cl_generator import CoverLetterGenerator, select_tone_variant
from .llm_client import LLMClient
from .cv_tailor import CVTailor
from .docx_cl_builder import DocxCLBuilder
from .docx_cv_builder import DocxCVBuilder
from .jd_analyser import JDAnalyser
from .master_cv_store import MasterCVMissingError, load_master_cv

logger = logging.getLogger(__name__)

# ATS score threshold — re-tailor if below this
_ATS_THRESHOLD = 75


def _load_master_cv() -> dict[str, Any]:
    return load_master_cv()


def _load_personal() -> dict[str, Any]:
    return load_master_cv().get("personal", {})


def _master_cv_text(master: dict[str, Any]) -> str:
    """Flatten master CV to a single lowercased string for keyword containment checks."""
    parts: list[str] = []
    for exp in master.get("experience", []):
        if isinstance(exp, dict):
            parts.extend([exp.get("role", ""), exp.get("company", "")])
            for ach in exp.get("achievements", []):
                parts.append(ach.get("text", "") if isinstance(ach, dict) else str(ach))
    skills = master.get("skills", {})
    if isinstance(skills, dict):
        for grp in skills.values():
            if isinstance(grp, dict):
                parts.extend(grp.get("items", []))
    elif isinstance(skills, list):
        for grp in skills:
            if isinstance(grp, dict):
                parts.extend(grp.get("items", []))
    parts.extend(master.get("certifications", []))
    return " ".join(str(p) for p in parts if p).lower()


def _partition_ats_keywords(
    missing_critical: list[str], master_text: str
) -> tuple[list[str], list[str]]:
    """Split missing ATS keywords into those grounded in master CV vs genuine gaps.

    Returns:
        (grounded, gaps) — grounded keywords can be reinforced in re-tailoring;
        gaps are honest skill gaps the user needs to fill themselves.
    """
    grounded: list[str] = []
    gaps: list[str] = []
    for kw in missing_critical:
        if kw.lower() in master_text:
            grounded.append(kw)
        else:
            gaps.append(kw)
    return grounded, gaps


class TailorService:
    """Orchestrates JD analysis → CV tailoring → ATS scoring → docx generation."""

    def __init__(self) -> None:
        self._claude = LLMClient()
        self._jd_analyser = JDAnalyser(self._claude)
        self._cv_tailor = CVTailor(self._claude)
        self._cl_generator = CoverLetterGenerator(self._claude)
        self._ats_optimiser = ATSOptimiser(self._claude)
        self._cv_builder = DocxCVBuilder()
        self._cl_builder = DocxCLBuilder()

    async def analyse_job(self, job_id: str, db: AsyncSession) -> JDAnalysisResponse:
        """Run JD analysis for a job posting and compute skill match.

        Args:
            job_id: UUID of the JobPosting record.
            db: Active async DB session.

        Returns:
            JDAnalysisResponse with analysis + skill_match.

        Raises:
            HTTPException 404 if job not found.
        """
        try:
            analysis = await self._jd_analyser.analyse_from_job_posting(job_id, db)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        master_cv = _load_master_cv()
        skill_match = self._jd_analyser.compute_skill_match(analysis, master_cv)

        return JDAnalysisResponse(
            job_id=job_id,
            analysis=analysis,
            skill_match=skill_match,
        )

    async def analyse_jd_text(self, job_description: str, job_url: str | None = None) -> JDAnalysisResponse:
        """Analyse a raw JD text (not tied to a saved job posting).

        Args:
            job_description: Raw JD text.
            job_url: Optional URL to fetch text from if description is empty.

        Returns:
            JDAnalysisResponse.
        """
        analysis = await self._jd_analyser.analyse(job_description, job_url)
        master_cv = _load_master_cv()
        skill_match = self._jd_analyser.compute_skill_match(analysis, master_cv)
        return JDAnalysisResponse(
            job_id="adhoc",
            analysis=analysis,
            skill_match=skill_match,
        )

    async def generate_cv(
        self,
        application_id: str,
        variant: str,
        jd_text: str,
        db: AsyncSession,
        custom_instructions: str | None = None,
    ) -> GeneratedDocumentRead:
        """Generate a tailored CV and persist the document record.

        Applies one re-tailoring pass if initial ATS score < threshold.

        Args:
            application_id: UUID of the Application.
            variant: "A" or "B".
            jd_text: Full job description text.
            db: Active async DB session.
            custom_instructions: Optional extra guidance for Claude.

        Returns:
            GeneratedDocumentRead for the saved .docx record.
        """
        doc_repo = DocumentRepository(db)
        analysis = await self._jd_analyser.analyse(jd_text)
        tailored_cv = await self._cv_tailor.tailor(analysis, variant, custom_instructions)

        # G-3: blocking grounding issues withhold the document entirely
        if tailored_cv.blocking_issues:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "Tailored CV failed grounding checks — document withheld.",
                    "issues": tailored_cv.blocking_issues,
                    "hint": "Fix the issues in your master CV or re-run tailoring.",
                },
            )

        # ATS score check + G-6 grounded retry
        cv_text = _cv_to_plain_text(tailored_cv)
        ats_result = await self._ats_optimiser.score(cv_text, analysis)

        if ats_result.overall_score < _ATS_THRESHOLD:
            logger.info(
                "ATS score %d < %d — applying grounded improvements and re-tailoring",
                ats_result.overall_score, _ATS_THRESHOLD,
            )
            master_text = _master_cv_text(_load_master_cv())
            grounded, gaps = _partition_ats_keywords(ats_result.missing_critical, master_text)
            if gaps:
                logger.info(
                    "G-6: ATS retry — %d keyword(s) are genuine skill gaps (not in master CV), "
                    "excluded from re-tailor instructions: %s",
                    len(gaps), gaps,
                )
            if grounded:
                grounded_instruction = (
                    f"Increase coverage of these keywords which the candidate already has: "
                    f"{', '.join(grounded)}. Do not introduce any other new terms."
                )
            else:
                grounded_instruction = (
                    "Improve flow and ATS formatting. "
                    "Do not introduce any keywords not already in the master CV."
                )
            other_suggestions = [
                s for s in self._ats_optimiser.suggest_improvements(ats_result)
                if not s.startswith("CRITICAL:")
            ]
            improvements = "\n".join([grounded_instruction] + other_suggestions[:3])
            tailored_cv = await self._cv_tailor.tailor(
                analysis, variant, f"{custom_instructions or ''}\n{improvements}"
            )
            # G-3: also check the re-tailored result
            if tailored_cv.blocking_issues:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "Re-tailored CV still failed grounding checks — document withheld.",
                        "issues": tailored_cv.blocking_issues,
                        "hint": "Fix the issues in your master CV or re-run tailoring.",
                    },
                )
            cv_text = _cv_to_plain_text(tailored_cv)
            ats_result = await self._ats_optimiser.score(cv_text, analysis)

        personal = _load_personal()
        version = await doc_repo.get_latest_version(application_id, "cv") + 1
        file_path, file_size = self._cv_builder.build(
            tailored_cv, analysis, personal, application_id, version, variant
        )

        doc = await doc_repo.create(
            application_id=application_id,
            document_type="cv",
            version=version,
            file_path=file_path,
            file_size_bytes=file_size,
            jd_analysis_snapshot=json.dumps(analysis.model_dump()),
            tailoring_params=json.dumps({"variant": variant, "custom_instructions": custom_instructions}),
            ats_score=ats_result.overall_score,
            ats_details=json.dumps(ats_result.model_dump()),
            variant_label=variant,
            status="generated",
        )
        await db.commit()
        return doc

    async def generate_cover_letter(
        self,
        application_id: str,
        variant: str,
        jd_text: str,
        db: AsyncSession,
    ) -> GeneratedDocumentRead:
        """Generate a tailored cover letter and persist the document record.

        Args:
            application_id: UUID of the Application.
            variant: "A" or "B".
            jd_text: Full job description text.
            db: Active async DB session.

        Returns:
            GeneratedDocumentRead for the saved .docx record.
        """
        doc_repo = DocumentRepository(db)
        analysis = await self._jd_analyser.analyse(jd_text)
        tailored_cv = await self._cv_tailor.tailor(analysis, variant)

        # G-3: blocking grounding issues withhold the document entirely
        if tailored_cv.blocking_issues:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "Tailored CV failed grounding checks — cover letter withheld.",
                    "issues": tailored_cv.blocking_issues,
                    "hint": "Fix the issues in your master CV or re-run tailoring.",
                },
            )

        personal = _load_personal()
        cl_variant = select_tone_variant(analysis)
        cover_letter = await self._cl_generator.generate(analysis, tailored_cv, personal, cl_variant)

        version = await doc_repo.get_latest_version(application_id, "cover_letter") + 1
        file_path, file_size = self._cl_builder.build(
            cover_letter, analysis, personal, application_id, version, variant
        )

        doc = await doc_repo.create(
            application_id=application_id,
            document_type="cover_letter",
            version=version,
            file_path=file_path,
            file_size_bytes=file_size,
            jd_analysis_snapshot=json.dumps(analysis.model_dump()),
            tailoring_params=json.dumps({"variant": variant}),
            variant_label=variant,
            status="generated",
        )
        await db.commit()
        return doc

    async def _create_manual_application(
        self,
        job_title: str,
        company_name: str | None,
        job_url: str | None,
        jd_text: str | None,
        db: AsyncSession,
    ) -> str:
        """Create a JobPosting + Application for a manually-sourced internet job.

        If a JobPosting already exists for the given URL it is reused (no
        duplicate created). A new Application is always created so each
        tailoring attempt is independently tracked.

        Returns:
            The new Application UUID (string).
        """
        from ..models.job import JobPosting  # noqa: PLC0415
        from ..models.application import Application  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415

        effective_url = job_url or f"manual://{uuid.uuid4()}"

        result = await db.execute(
            select(JobPosting).where(JobPosting.url == effective_url)
        )
        job = result.scalar_one_or_none()

        if job is None:
            job = JobPosting(
                id=str(uuid.uuid4()),
                title=job_title or "Manual Job",
                company=company_name,
                url=effective_url,
                source="manual",
                description=jd_text,
            )
            db.add(job)
            await db.flush()

        app = Application(
            id=str(uuid.uuid4()),
            job_id=job.id,
            status="discovered",
            agent_created=False,
            approval_status="pending",
            notes="Created via Resume Tailoring page",
        )
        db.add(app)
        await db.flush()
        await db.commit()
        logger.info("Auto-created application %s for manual job '%s'", app.id, job.title)
        return app.id

    async def generate_all(
        self,
        application_id: str | None,
        variant: str,
        jd_text: str,
        db: AsyncSession,
        generate_variants: bool = False,
        job_title: str | None = None,
        company_name: str | None = None,
        job_url: str | None = None,
    ) -> TailorResultBundle:
        """Run the full pipeline: JD analysis → CV → Cover letter.

        Args:
            application_id: UUID of an existing Application, or None to
                auto-create a pipeline entry from the job metadata below.
            variant: "A" or "B".
            jd_text: Full JD text.
            db: Active async DB session.
            generate_variants: If True, also generate variant B.
            job_title: Used only when application_id is None.
            company_name: Used only when application_id is None.
            job_url: Used only when application_id is None.

        Returns:
            TailorResultBundle with document IDs and scores.
        """
        if not application_id:
            application_id = await self._create_manual_application(
                job_title=job_title or "Manual Job",
                company_name=company_name,
                job_url=job_url,
                jd_text=jd_text,
                db=db,
            )
        # Auto-resolve JD from the linked job posting when caller omits jd_text
        if not jd_text and application_id:
            from sqlalchemy import select  # noqa: PLC0415
            from ..models.application import Application  # noqa: PLC0415
            from ..models.job import JobPosting  # noqa: PLC0415
            app_r = await db.execute(select(Application).where(Application.id == application_id))
            _app = app_r.scalar_one_or_none()
            if _app and _app.job_id:
                job_r = await db.execute(select(JobPosting).where(JobPosting.id == _app.job_id))
                _job = job_r.scalar_one_or_none()
                if _job:
                    jd_text = _job.description or _job.title or ""
                    if not job_url:
                        job_url = _job.url
        analysis = await self._jd_analyser.analyse(jd_text, job_url)
        master_cv = _load_master_cv()
        skill_match = self._jd_analyser.compute_skill_match(analysis, master_cv)

        cv_doc = await self.generate_cv(application_id, variant, jd_text, db)
        cl_doc = await self.generate_cover_letter(application_id, variant, jd_text, db)

        # Fetch the ATS score we stored on cv_doc
        doc_repo = DocumentRepository(db)
        cv_full = await doc_repo.get_by_id(cv_doc.id)
        ats_result: ATSScoreResult | None = None
        if cv_full and cv_full.ats_details:
            try:
                ats_result = ATSScoreResult(**json.loads(cv_full.ats_details))
            except Exception:
                pass

        return TailorResultBundle(
            application_id=application_id,
            cv_document_id=cv_doc.id,
            cl_document_id=cl_doc.id,
            ats_score=ats_result,
            analysis=analysis,
            skill_match=skill_match,
        )

    async def stream_progress(
        self,
        application_id: str,
        variant: str,
        jd_text: str,
        db: AsyncSession,
    ) -> AsyncGenerator[str, None]:
        """Yield SSE events for the full pipeline, then generate documents.

        Yields:
            Server-Sent Events strings like "data: {...}\n\n"
        """

        def sse(stage: str, pct: int, message: str = "") -> str:
            payload = json.dumps({"stage": stage, "pct": pct, "message": message})
            return f"data: {payload}\n\n"

        yield sse("analysing_jd", 10, "Analysing job description...")
        analysis = await self._jd_analyser.analyse(jd_text)

        yield sse("skill_match", 25, "Computing skill match...")
        master_cv = _load_master_cv()
        self._jd_analyser.compute_skill_match(analysis, master_cv)

        yield sse("tailoring_cv", 40, "Tailoring CV with Claude...")
        tailored_cv = await self._cv_tailor.tailor(analysis, variant)

        # G-3: blocking grounding issues withhold the document
        if tailored_cv.blocking_issues:
            yield sse(
                "error",
                0,
                json.dumps({
                    "error": "Tailored CV failed grounding checks — document withheld.",
                    "issues": tailored_cv.blocking_issues,
                }),
            )
            return

        yield sse("scoring_ats", 55, "Running ATS scoring...")
        cv_text = _cv_to_plain_text(tailored_cv)
        ats_result = await self._ats_optimiser.score(cv_text, analysis)

        if ats_result.overall_score < _ATS_THRESHOLD:
            yield sse("improving_cv", 65, f"ATS score {ats_result.overall_score} — optimising...")
            master_text = _master_cv_text(_load_master_cv())
            grounded, gaps = _partition_ats_keywords(ats_result.missing_critical, master_text)
            if grounded:
                grounded_instruction = (
                    f"Increase coverage of these keywords which the candidate already has: "
                    f"{', '.join(grounded)}. Do not introduce any other new terms."
                )
            else:
                grounded_instruction = (
                    "Improve flow and ATS formatting. "
                    "Do not introduce any keywords not already in the master CV."
                )
            other_suggestions = [
                s for s in self._ats_optimiser.suggest_improvements(ats_result)
                if not s.startswith("CRITICAL:")
            ]
            improvements = "\n".join([grounded_instruction] + other_suggestions[:3])
            tailored_cv = await self._cv_tailor.tailor(analysis, variant, improvements)
            if tailored_cv.blocking_issues:
                yield sse(
                    "error",
                    0,
                    json.dumps({
                        "error": "Re-tailored CV still failed grounding checks — document withheld.",
                        "issues": tailored_cv.blocking_issues,
                    }),
                )
                return
            cv_text = _cv_to_plain_text(tailored_cv)
            ats_result = await self._ats_optimiser.score(cv_text, analysis)

        yield sse("generating_cl", 70, "Generating cover letter...")
        personal = _load_personal()
        cl_variant = select_tone_variant(analysis)
        cover_letter = await self._cl_generator.generate(analysis, tailored_cv, personal, cl_variant)

        yield sse("building_docx", 85, "Building .docx documents...")
        doc_repo = DocumentRepository(db)

        cv_version = await doc_repo.get_latest_version(application_id, "cv") + 1
        cv_path, cv_size = self._cv_builder.build(
            tailored_cv, analysis, personal, application_id, cv_version, variant
        )
        cv_doc = await doc_repo.create(
            application_id=application_id,
            document_type="cv",
            version=cv_version,
            file_path=cv_path,
            file_size_bytes=cv_size,
            jd_analysis_snapshot=json.dumps(analysis.model_dump()),
            tailoring_params=json.dumps({"variant": variant}),
            ats_score=ats_result.overall_score,
            ats_details=json.dumps(ats_result.model_dump()),
            variant_label=variant,
        )

        cl_version = await doc_repo.get_latest_version(application_id, "cover_letter") + 1
        cl_path, cl_size = self._cl_builder.build(
            cover_letter, analysis, personal, application_id, cl_version, variant
        )
        cl_doc = await doc_repo.create(
            application_id=application_id,
            document_type="cover_letter",
            version=cl_version,
            file_path=cl_path,
            file_size_bytes=cl_size,
            jd_analysis_snapshot=json.dumps(analysis.model_dump()),
            tailoring_params=json.dumps({"variant": variant}),
            variant_label=variant,
        )

        await db.commit()

        yield sse(
            "complete",
            100,
            json.dumps({
                "cv_document_id": cv_doc.id,
                "cl_document_id": cl_doc.id,
                "ats_score": ats_result.overall_score,
            }),
        )

    async def get_document_history(
        self, application_id: str, doc_type: str | None, db: AsyncSession
    ) -> list[GeneratedDocumentRead]:
        """Return all documents for an application.

        Args:
            application_id: UUID of the application.
            doc_type: Filter by "cv" or "cover_letter", or None for all.
            db: Active async DB session.

        Returns:
            List of GeneratedDocumentRead, newest first.
        """

        doc_repo = DocumentRepository(db)
        items = await doc_repo.list_by_application(application_id, doc_type)
        # Convert DocumentListItem → GeneratedDocumentRead via id lookups
        results: list[GeneratedDocumentRead] = []
        for item in items:
            full = await doc_repo.get_by_id(item.id)
            if full:
                results.append(full)
        return results

    async def download_document(self, document_id: str, db: AsyncSession) -> tuple[str, str]:
        """Return (file_path, filename) for a generated document.

        Args:
            document_id: UUID of the document.
            db: Active async DB session.

        Returns:
            Tuple of (absolute file path, filename for Content-Disposition).

        Raises:
            HTTPException 404 if document or file not found.
        """
        doc_repo = DocumentRepository(db)
        doc = await doc_repo.get_by_id(document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        file_path = doc.file_path
        if not file_path or not Path(file_path).exists():
            raise HTTPException(status_code=404, detail="Document file not found on disk")

        filename = Path(file_path).name
        return file_path, filename


def _cv_to_plain_text(tailored_cv: Any) -> str:
    """Convert a TailoredCVResult to plain text for ATS scoring."""
    parts = [tailored_cv.summary]
    for skill_group in tailored_cv.skills:
        if isinstance(skill_group, dict):
            parts.append(skill_group.get("display_name", ""))
            parts.extend(skill_group.get("items", []))
    for exp in tailored_cv.experience:
        parts.append(f"{exp.role} at {exp.company} ({exp.period})")
        parts.extend(exp.achievements)
    parts.extend(tailored_cv.certifications)
    return " ".join(str(p) for p in parts if p)
