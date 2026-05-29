"""AssistedApplyService — prepares tailored CV and cover letter for a job application.

This service ONLY prepares documents for human review.
It does NOT submit anything, fill forms, or post to job boards.
The user always makes the final click.

Status flow: approved → preparing → ready_to_apply
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# profile_loader is imported lazily inside prepare_application to avoid
# circular imports at module load time; it is bound here for testability.
try:
    from ..agents.tools.profile_loader import load_profile
except Exception:  # pragma: no cover — only fails in isolated unit test contexts
    load_profile = None  # type: ignore[assignment]


@dataclass
class ApplicationPackage:
    """Bundle of prepared application materials ready for human review."""

    job_id: str
    job_url: str
    cv_path: str | None         # path to generated tailored CV (.docx), or None if unavailable
    cover_letter_path: str | None
    prefill_map: dict[str, str] = field(default_factory=dict)  # name, email, phone from profile


class AssistedApplyService:
    """Prepares application documents (CV + cover letter) for a specific job.

    IMPORTANT: This service has NO submit(), NO browser_fill(), and makes NO
    HTTP POST requests to any job board. It only returns document paths and
    prefill data so the user can review everything before applying themselves.
    """

    async def prepare_application(
        self,
        job_id: str,
        db: AsyncSession,
    ) -> ApplicationPackage:
        """Tailor CV + cover letter for this job; return paths and prefill map.

        Steps:
        1. Load job from DB
        2. Load user profile
        3. Build prefill_map (name, email if present, phone etc.)
        4. Attempt tailor service for CV + CL (graceful fallback on failure)
        5. Update application status to "ready_to_apply"
        6. Return ApplicationPackage

        Args:
            job_id: UUID of the job posting to prepare for.
            db: Active async DB session.

        Returns:
            ApplicationPackage with cv_path, cover_letter_path, job_url, prefill_map.
        """
        from sqlalchemy import select, update
        from datetime import datetime

        from ..models.job import JobPosting
        from ..models.application import Application

        # 1. Load job
        job_result = await db.execute(
            select(JobPosting).where(JobPosting.id == job_id)
        )
        job = job_result.scalar_one_or_none()
        job_url = job.url if job else ""

        # 2. Load profile (module-level reference for easy mocking in tests)
        try:
            _lp = load_profile
            profile = _lp() if callable(_lp) else None
            name = getattr(getattr(profile, "candidate", None), "name", None) or ""
            email_val = getattr(getattr(profile, "candidate", None), "email", None)
            phone_val = getattr(getattr(profile, "candidate", None), "phone", None)
        except Exception:
            profile = None
            name = ""
            email_val = None
            phone_val = None

        # 3. Build prefill_map
        prefill_map: dict[str, str] = {}
        if name:
            prefill_map["name"] = name
        if email_val:
            prefill_map["email"] = str(email_val)
        if phone_val:
            prefill_map["phone"] = str(phone_val)

        # 4. Mark status as "preparing"
        await db.execute(
            update(Application)
            .where(Application.job_id == job_id)
            .values(status="preparing", updated_at=datetime.utcnow())
        )

        # 5. Attempt to tailor CV + CL (wrap gracefully)
        cv_path: str | None = None
        cover_letter_path: str | None = None

        try:
            from ..services.tailor_service import TailorService

            tailor = TailorService()
            if job is not None:
                jd_text = job.description or f"{job.title} at {job.company}"
                result = await tailor.generate_all(
                    job_id=job_id,
                    jd_text=jd_text,
                )
                cv_path = getattr(result, "cv_path", None)
                cover_letter_path = getattr(result, "cover_letter_path", None)
        except Exception as exc:
            logger.warning(
                "Tailor service unavailable for job %s, continuing without docs: %s",
                job_id,
                exc,
            )

        # 6. Update status to "ready_to_apply"
        await db.execute(
            update(Application)
            .where(Application.job_id == job_id)
            .values(status="ready_to_apply", updated_at=datetime.utcnow())
        )
        await db.commit()

        return ApplicationPackage(
            job_id=job_id,
            job_url=job_url,
            cv_path=cv_path,
            cover_letter_path=cover_letter_path,
            prefill_map=prefill_map,
        )

    # ─────────────────────────────────────────────────────────────
    # NOTE: There is intentionally NO submit() method here.
    # NOTE: There is intentionally NO browser_fill() method here.
    # NOTE: There are NO HTTP requests to job board URLs.
    # The user is ALWAYS in control of the final submission click.
    # ─────────────────────────────────────────────────────────────
