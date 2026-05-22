"""ReminderService — checks overdue follow-ups and auto-drafts follow-up emails."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.application import Application, FollowUp, InterviewRound
from ..models.follow_up_email import FollowUpEmail
from ..repositories.application_repository import ApplicationRepository

if TYPE_CHECKING:
    from .email_generator import EmailGenerator

logger = logging.getLogger(__name__)


class ReminderService:
    """Scheduled service that logs warnings for overdue follow-ups and auto-drafts emails."""

    def __init__(
        self,
        app_repo: ApplicationRepository,
        email_generator: "EmailGenerator | None" = None,
    ) -> None:
        self._repo = app_repo
        self._email_gen = email_generator

    async def check_overdue(self) -> int:
        """Log warnings for all overdue follow-ups and return the count found.

        Returns:
            Count of overdue follow-ups found.
        """
        overdue = await self._repo.get_overdue_follow_ups()
        if overdue:
            logger.warning(
                "ReminderService: %d overdue follow-up(s) found.",
                len(overdue),
            )
            for fu in overdue:
                logger.warning(
                    "  [OVERDUE] app_id=%s type=%s due=%s",
                    fu.application_id,
                    fu.type,
                    fu.due_date.isoformat(),
                )
        return len(overdue)

    async def check_and_draft_emails(self, db: AsyncSession) -> int:
        """For each overdue follow-up, auto-draft an email if one doesn't exist yet.

        Requires email_generator to be set (pass at construction time).

        Args:
            db: Async database session.

        Returns:
            Count of new email drafts created.
        """
        if self._email_gen is None:
            return 0

        now = datetime.utcnow()
        overdue = await self._repo.get_overdue_follow_ups()
        drafted = 0

        for fu in overdue:
            try:
                # Check if a draft email already exists for this follow-up
                existing = await db.execute(
                    select(FollowUpEmail).where(
                        FollowUpEmail.application_id == fu.application_id,
                        FollowUpEmail.follow_up_id == fu.id,
                        FollowUpEmail.status == "draft",
                    )
                )
                if existing.scalars().first():
                    continue  # already has a pending draft

                # Load the application and job
                app_result = await db.execute(
                    select(Application).where(Application.id == fu.application_id)
                )
                application = app_result.scalars().first()
                if application is None or not application.job_id:
                    continue

                from ..models.job import JobPosting  # noqa: PLC0415
                job_result = await db.execute(
                    select(JobPosting).where(JobPosting.id == application.job_id)
                )
                job = job_result.scalars().first()
                if job is None:
                    continue

                # Determine email type based on follow-up type and age
                days_since_applied = 0
                if application.applied_date:
                    days_since_applied = (now - application.applied_date).days
                else:
                    days_since_applied = (now - application.created_at).days

                email_type = fu.type  # use follow_up.type as hint
                if fu.type == "thank_you":
                    # Find the latest completed interview
                    interview_result = await db.execute(
                        select(InterviewRound)
                        .where(
                            InterviewRound.application_id == application.id,
                            InterviewRound.status == "completed",
                        )
                        .order_by(InterviewRound.updated_at.desc())
                    )
                    interview = interview_result.scalars().first()
                    if interview:
                        generated = await self._email_gen.generate_post_interview_thankyou(
                            application, job, interview
                        )
                    else:
                        generated = await self._email_gen.generate_warm_reengagement(
                            application, job, days_since_applied
                        )
                elif days_since_applied >= 14:
                    generated = await self._email_gen.generate_warm_reengagement(
                        application, job, days_since_applied
                    )
                else:
                    generated = await self._email_gen.generate_post_application(
                        application, job, days_since_applied
                    )

                draft = self._email_gen.save_draft(
                    email=generated,
                    application=application,
                    generation_params={
                        "follow_up_id": fu.id,
                        "email_type": generated.email_type,
                        "days_since_applied": days_since_applied,
                        "triggered_by": "reminder_check",
                    },
                    follow_up_id=fu.id,
                )
                db.add(draft)
                await db.flush()
                drafted += 1
                logger.info(
                    "Drafted %s email for application %s (follow_up %s)",
                    generated.email_type,
                    application.id,
                    fu.id,
                )

            except Exception as exc:
                logger.error(
                    "Failed to draft email for follow_up %s: %s", fu.id, exc
                )

        if drafted:
            await db.commit()
        return drafted

    async def check_thank_you_emails(self, db: AsyncSession) -> int:
        """Find completed interviews with no thank-you email draft and generate one.

        Runs every 2 hours to catch interviews completed since the last run.

        Args:
            db: Async database session.

        Returns:
            Count of new thank-you email drafts created.
        """
        if self._email_gen is None:
            return 0

        cutoff = datetime.utcnow() - timedelta(hours=2)

        # Find recently completed interviews with no thank-you email
        result = await db.execute(
            select(InterviewRound).where(
                InterviewRound.status == "completed",
                InterviewRound.updated_at >= cutoff,
            )
        )
        interviews = result.scalars().all()
        drafted = 0

        for interview in interviews:
            try:
                # Check if a thank-you email draft already exists
                existing = await db.execute(
                    select(FollowUpEmail).where(
                        FollowUpEmail.application_id == interview.application_id,
                        FollowUpEmail.email_type == "post_interview_thankyou",
                        FollowUpEmail.status.in_(["draft", "approved", "sent"]),
                    )
                )
                if existing.scalars().first():
                    continue

                app_result = await db.execute(
                    select(Application).where(Application.id == interview.application_id)
                )
                application = app_result.scalars().first()
                if application is None or not application.job_id:
                    continue

                from ..models.job import JobPosting  # noqa: PLC0415
                job_result = await db.execute(
                    select(JobPosting).where(JobPosting.id == application.job_id)
                )
                job = job_result.scalars().first()
                if job is None:
                    continue

                generated = await self._email_gen.generate_post_interview_thankyou(
                    application, job, interview
                )
                draft = self._email_gen.save_draft(
                    email=generated,
                    application=application,
                    generation_params={
                        "interview_id": interview.id,
                        "interview_type": interview.type,
                        "triggered_by": "thank_you_check",
                    },
                )
                db.add(draft)
                await db.flush()
                drafted += 1
                logger.info(
                    "Drafted thank-you email for interview %s (application %s)",
                    interview.id,
                    application.id,
                )

            except Exception as exc:
                logger.error(
                    "Failed to draft thank-you email for interview %s: %s",
                    interview.id,
                    exc,
                )

        if drafted:
            await db.commit()
        return drafted
