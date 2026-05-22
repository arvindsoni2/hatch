"""Daily digest email service — assembles and sends the JobPilot morning briefing."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.application import Application, FollowUp, InterviewRound
from ..models.auto_apply import ApplicationAttempt
from ..models.job import JobPosting

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "emails"

_jinja = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(enabled_extensions=("html",)),
    trim_blocks=True,
    lstrip_blocks=True,
)


class DigestService:
    """Builds and sends the daily job digest email."""

    def __init__(self, claude_client: object = None) -> None:  # claude_client unused for now
        pass

    async def build_digest(self, db: AsyncSession) -> dict[str, Any]:
        """Assemble digest payload from the database.

        Args:
            db: Async SQLAlchemy session.

        Returns:
            Dict with keys: date, stats, top_jobs, follow_ups, interviews,
            auto_apply_results.
        """
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(hours=24)
        this_week_end = now + timedelta(days=7)

        # Top new jobs with match score >= threshold, last 24h
        jobs_result = await db.execute(
            select(JobPosting)
            .where(
                JobPosting.is_active.is_(True),
                JobPosting.scraped_at >= yesterday,
                JobPosting.match_score >= settings.MATCH_SCORE_MIN_FOR_DIGEST,
            )
            .order_by(JobPosting.match_score.desc())
            .limit(10)
        )
        top_jobs = [
            {
                "title": j.title,
                "company": j.company,
                "location": j.location,
                "rate_text": j.rate_text,
                "url": j.url,
                "match_score": j.match_score,
                "match_reasons": j.match_reasons or [],
                "working_pattern": j.working_pattern,
                "ir35_status": j.ir35_status,
            }
            for j in jobs_result.scalars().all()
        ]

        # Pipeline stats
        applied_result = await db.execute(
            select(Application).where(Application.status == "applied", Application.is_active.is_(True))
        )
        interview_result = await db.execute(
            select(Application).where(Application.status.in_(["interview", "technical_test"]), Application.is_active.is_(True))
        )
        offered_result = await db.execute(
            select(Application).where(Application.status == "offered", Application.is_active.is_(True))
        )
        stats = {
            "applied": len(list(applied_result.scalars().all())),
            "interview": len(list(interview_result.scalars().all())),
            "offered": len(list(offered_result.scalars().all())),
            "new_jobs": len(top_jobs),
        }

        # Follow-ups due today
        today_end = now.replace(hour=23, minute=59, second=59)
        followups_result = await db.execute(
            select(FollowUp)
            .where(
                FollowUp.completed.is_(False),
                FollowUp.due_date <= today_end,
            )
            .limit(10)
        )
        followups_list = list(followups_result.scalars().all())

        # Batch-fetch applications for all follow-ups (avoids N+1)
        followup_app_ids = [f.application_id for f in followups_list if f.application_id]
        if followup_app_ids:
            fu_apps_result = await db.execute(
                select(Application).where(Application.id.in_(followup_app_ids))
            )
            fu_apps_by_id: dict[str, Application] = {
                a.id: a for a in fu_apps_result.scalars().all()
            }
        else:
            fu_apps_by_id = {}

        follow_ups = [
            {
                "company": fu_apps_by_id.get(f.application_id, None) and fu_apps_by_id[f.application_id].agency_name,
                "note": f.note,
                "type": f.type,
                "due_date": f.due_date.strftime("%d %b %Y") if f.due_date else "",
            }
            for f in followups_list
        ]

        # Upcoming interviews this week
        interviews_result = await db.execute(
            select(InterviewRound)
            .where(
                InterviewRound.scheduled_at >= now,
                InterviewRound.scheduled_at <= this_week_end,
                InterviewRound.status == "scheduled",
            )
            .order_by(InterviewRound.scheduled_at)
            .limit(5)
        )
        interviews_list = list(interviews_result.scalars().all())

        # Batch-fetch applications for all interviews (avoids N+1)
        interview_app_ids = [i.application_id for i in interviews_list if i.application_id]
        if interview_app_ids:
            iv_apps_result = await db.execute(
                select(Application).where(Application.id.in_(interview_app_ids))
            )
            iv_apps_by_id: dict[str, Application] = {
                a.id: a for a in iv_apps_result.scalars().all()
            }
        else:
            iv_apps_by_id = {}

        interviews = [
            {
                "company": iv_apps_by_id.get(i.application_id, None) and iv_apps_by_id[i.application_id].agency_name,
                "round_number": i.round_number,
                "type": i.type,
                "scheduled_at": i.scheduled_at.strftime("%a %d %b %Y %H:%M") if i.scheduled_at else "",
            }
            for i in interviews_list
        ]

        # Auto-apply results last 24h
        auto_result = await db.execute(
            select(ApplicationAttempt)
            .where(ApplicationAttempt.created_at >= yesterday)
            .order_by(ApplicationAttempt.created_at.desc())
            .limit(10)
        )
        auto_apply_results = [
            {
                "job_url": a.job_url,
                "job_title": None,  # Would require join — left as URL for now
                "platform": a.platform,
                "status": a.status,
            }
            for a in auto_result.scalars().all()
        ]

        return {
            "date": now.strftime("%A, %d %B %Y"),
            "stats": stats,
            "top_jobs": top_jobs,
            "follow_ups": follow_ups,
            "interviews": interviews,
            "auto_apply_results": auto_apply_results,
        }

    async def preview_html(self, db: AsyncSession) -> str:
        """Render digest HTML without sending.

        Args:
            db: Async SQLAlchemy session.

        Returns:
            Rendered HTML string.
        """
        payload = await self.build_digest(db)
        template = _jinja.get_template("daily_digest.html")
        return template.render(**payload)

    async def send(self, db: AsyncSession) -> bool:
        """Build and send the digest email.

        Skips silently if SMTP_USER is not configured or there is nothing to report.

        Args:
            db: Async SQLAlchemy session.

        Returns:
            True if sent, False if skipped.
        """
        if not settings.SMTP_USER or not settings.NOTIFICATION_EMAIL:
            logger.info("Digest: SMTP_USER or NOTIFICATION_EMAIL not set — skipping.")
            return False

        payload = await self.build_digest(db)

        if not payload["top_jobs"] and not payload["follow_ups"] and not payload["interviews"]:
            logger.info("Digest: nothing to report — skipping.")
            return False

        html_body = _jinja.get_template("daily_digest.html").render(**payload)

        try:
            import aiosmtplib  # type: ignore[import]
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"JobPilot Digest — {payload['date']}"
            msg["From"] = settings.SMTP_USER
            msg["To"] = settings.NOTIFICATION_EMAIL
            msg.attach(MIMEText(html_body, "html"))

            await aiosmtplib.send(
                msg,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                start_tls=True,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASS,
            )
            logger.info("Digest sent to %s", settings.NOTIFICATION_EMAIL)
            return True

        except ImportError:
            logger.warning("aiosmtplib not installed — cannot send digest email.")
            return False
        except Exception as exc:
            logger.error("Digest email send failed: %s", exc)
            return False
