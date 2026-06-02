"""API endpoints for follow-up email drafting, review, and sending."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.application import Application, InterviewRound
from ..models.follow_up_email import FollowUpEmail
from ..models.job import JobPosting
from ..schemas.email import (
    EmailGenerateRequest,
    EmailSendRequest,
    EmailSendResponse,
    EmailStats,
    EmailUpdateRequest,
    FollowUpEmailListItem,
    FollowUpEmailRead,
)
from ..services.async_job_service import AsyncJobService
from ..services.claude_client import ClaudeClient
from ..services.email_generator import EmailGenerator
from ..services.email_sender import EmailRateLimitError, EmailSender

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/emails", tags=["emails"])

_email_sender = EmailSender()


def _get_email_generator() -> EmailGenerator:
    return EmailGenerator(ClaudeClient())


def _to_read(email: FollowUpEmail, job_title: str = "", company: str = "") -> FollowUpEmailRead:
    return FollowUpEmailRead(
        id=email.id,
        application_id=email.application_id,
        follow_up_id=email.follow_up_id,
        email_type=email.email_type,
        recipient_email=email.recipient_email,
        recipient_name=email.recipient_name,
        subject=email.subject,
        body_html=email.body_html,
        body_plain=email.body_plain,
        status=email.status,
        sent_via=email.sent_via,
        sent_at=email.sent_at,
        opened_at=email.opened_at,
        created_at=email.created_at,
        job_title=job_title,
        company=company,
    )


async def _enrich(email: FollowUpEmail, db: AsyncSession) -> FollowUpEmailRead:
    """Denormalise job title and company onto the response."""
    job_title = company = ""
    if email.application_id:
        app_result = await db.execute(
            select(Application).where(Application.id == email.application_id)
        )
        app = app_result.scalars().first()
        if app and app.job_id:
            job_result = await db.execute(
                select(JobPosting).where(JobPosting.id == app.job_id)
            )
            job = job_result.scalars().first()
            if job:
                job_title = job.title or ""
                company = job.company or ""
    return _to_read(email, job_title, company)


# ─────────────────────── List Endpoints ───────────────────────


@router.get("/pending", response_model=list[FollowUpEmailListItem])
async def get_pending_emails(
    db: AsyncSession = Depends(get_db),
) -> list[FollowUpEmailListItem]:
    """Return all draft emails sorted by urgency.

    Urgency order: post_interview_thankyou first (24h window), then post_application,
    then warm_reengagement, then custom.
    """
    result = await db.execute(
        select(FollowUpEmail)
        .where(FollowUpEmail.status == "draft")
        .order_by(FollowUpEmail.created_at.asc())
    )
    emails = result.scalars().all()

    # Sort by urgency: thank-you first
    type_order = {
        "post_interview_thankyou": 0,
        "post_application": 1,
        "warm_reengagement": 2,
        "custom": 3,
    }
    emails = sorted(emails, key=lambda e: type_order.get(e.email_type, 99))

    items: list[FollowUpEmailListItem] = []
    for email in emails:
        job_title = company = ""
        app_result = await db.execute(
            select(Application).where(Application.id == email.application_id)
        )
        app = app_result.scalars().first()
        if app and app.job_id:
            job_result = await db.execute(
                select(JobPosting).where(JobPosting.id == app.job_id)
            )
            job = job_result.scalars().first()
            if job:
                job_title = job.title or ""
                company = job.company or ""
        items.append(
            FollowUpEmailListItem(
                id=email.id,
                application_id=email.application_id,
                email_type=email.email_type,
                recipient_email=email.recipient_email,
                subject=email.subject,
                status=email.status,
                created_at=email.created_at,
                job_title=job_title,
                company=company,
            )
        )
    return items


@router.get("/stats", response_model=EmailStats)
async def get_email_stats(db: AsyncSession = Depends(get_db)) -> EmailStats:
    """Return summary statistics for sent follow-up emails."""
    week_ago = datetime.utcnow() - timedelta(days=7)

    sent_week_result = await db.execute(
        select(func.count(FollowUpEmail.id)).where(
            FollowUpEmail.status == "sent",
            FollowUpEmail.sent_at >= week_ago,
        )
    )
    sent_week = sent_week_result.scalar() or 0

    sent_total_result = await db.execute(
        select(func.count(FollowUpEmail.id)).where(FollowUpEmail.status == "sent")
    )
    sent_total = sent_total_result.scalar() or 0

    pending_result = await db.execute(
        select(func.count(FollowUpEmail.id)).where(FollowUpEmail.status == "draft")
    )
    pending = pending_result.scalar() or 0

    # Per-type breakdown
    type_result = await db.execute(
        select(FollowUpEmail.email_type, func.count(FollowUpEmail.id))
        .where(FollowUpEmail.status == "sent")
        .group_by(FollowUpEmail.email_type)
    )
    by_type = {row[0]: row[1] for row in type_result.all()}

    return EmailStats(
        sent_this_week=sent_week,
        sent_total=sent_total,
        pending_drafts=pending,
        by_type=by_type,
    )


@router.get("/history", response_model=list[FollowUpEmailListItem])
async def get_email_history(
    application_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[FollowUpEmailListItem]:
    """Return sent/skipped emails, optionally filtered by application."""
    stmt = select(FollowUpEmail).where(
        FollowUpEmail.status.in_(["sent", "skipped", "failed"])
    )
    if application_id:
        stmt = stmt.where(FollowUpEmail.application_id == application_id)
    stmt = stmt.order_by(FollowUpEmail.created_at.desc())

    result = await db.execute(stmt)
    emails = result.scalars().all()
    return [
        FollowUpEmailListItem(
            id=e.id,
            application_id=e.application_id,
            email_type=e.email_type,
            recipient_email=e.recipient_email,
            subject=e.subject,
            status=e.status,
            created_at=e.created_at,
        )
        for e in emails
    ]


# ─────────────────────── Single Email Endpoints ───────────────────────


@router.get("/{email_id}", response_model=FollowUpEmailRead)
async def get_email(email_id: str, db: AsyncSession = Depends(get_db)) -> FollowUpEmailRead:
    """Return full email detail for review."""
    result = await db.execute(
        select(FollowUpEmail).where(FollowUpEmail.id == email_id)
    )
    email = result.scalars().first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    return await _enrich(email, db)


@router.patch("/{email_id}", response_model=FollowUpEmailRead)
async def update_email(
    email_id: str,
    body: EmailUpdateRequest,
    db: AsyncSession = Depends(get_db),
    generator: EmailGenerator = Depends(_get_email_generator),
) -> FollowUpEmailRead:
    """Update draft email fields (subject, body, recipient).

    When body text is updated, the HTML is re-rendered using the template.
    """
    result = await db.execute(
        select(FollowUpEmail).where(FollowUpEmail.id == email_id)
    )
    email = result.scalars().first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    if email.status not in ("draft", "approved"):
        raise HTTPException(status_code=400, detail=f"Cannot edit email in status '{email.status}'")

    if body.subject is not None:
        email.subject = body.subject
    if body.recipient_email is not None:
        email.recipient_email = body.recipient_email
    if body.recipient_name is not None:
        email.recipient_name = body.recipient_name
    if body.body is not None:
        # Re-render HTML from updated plain text via a GeneratedEmail shell
        from ..schemas.email import GeneratedEmail  # noqa: PLC0415
        shell = GeneratedEmail(
            email_type=email.email_type,
            subject=email.subject,
            greeting="",
            body=body.body,
            sign_off="Kind regards,",
        )
        email.body_plain = body.body
        email.body_html = generator.render_html(shell)

    await db.commit()
    await db.refresh(email)
    return await _enrich(email, db)


@router.post("/generate/{application_id}", status_code=202)
async def generate_email(
    application_id: str,
    body: EmailGenerateRequest,
    db: AsyncSession = Depends(get_db),
    generator: EmailGenerator = Depends(_get_email_generator),
) -> dict:
    """Kick off email generation. Poll /api/async-jobs/{job_id} for the draft."""
    async_job = await AsyncJobService.create(db, "email_generate")
    await db.commit()

    email_type = body.email_type

    async def _work() -> None:
        from ..database import AsyncSessionLocal  # noqa: PLC0415
        from ..models.application import Application, InterviewRound  # noqa: PLC0415
        from ..models.job import JobPosting  # noqa: PLC0415
        from datetime import datetime as dt  # noqa: PLC0415
        from sqlalchemy import select as sa_select  # noqa: PLC0415

        try:
            async with AsyncSessionLocal() as own_db:
                app_result = await own_db.execute(
                    sa_select(Application).where(Application.id == application_id)
                )
                application = app_result.scalars().first()
                if not application:
                    await AsyncJobService._finish(async_job.id, None, "Application not found")
                    return
                if not application.job_id:
                    await AsyncJobService._finish(async_job.id, None, "Application has no linked job")
                    return

                job_result = await own_db.execute(
                    sa_select(JobPosting).where(JobPosting.id == application.job_id)
                )
                job = job_result.scalars().first()
                if not job:
                    await AsyncJobService._finish(async_job.id, None, "Job not found")
                    return

                now = dt.utcnow()
                days_since = (
                    (now - application.applied_date).days if application.applied_date
                    else (now - application.created_at).days
                )

                if email_type == "post_application":
                    generated = await generator.generate_post_application(application, job, days_since)
                elif email_type == "post_interview_thankyou":
                    iv_result = await own_db.execute(
                        sa_select(InterviewRound)
                        .where(
                            InterviewRound.application_id == application_id,
                            InterviewRound.status == "completed",
                        )
                        .order_by(InterviewRound.updated_at.desc())
                    )
                    interview = iv_result.scalars().first()
                    if interview:
                        generated = await generator.generate_post_interview_thankyou(
                            application, job, interview
                        )
                    else:
                        generated = await generator.generate_warm_reengagement(
                            application, job, days_since
                        )
                elif email_type == "warm_reengagement":
                    generated = await generator.generate_warm_reengagement(application, job, days_since)
                else:
                    await AsyncJobService._finish(async_job.id, None, f"Unknown email_type: {email_type}")
                    return

                draft = generator.save_draft(
                    email=generated,
                    application=application,
                    generation_params={"email_type": email_type, "triggered_by": "manual"},
                )
                own_db.add(draft)
                await own_db.commit()
                await own_db.refresh(draft)

                enriched = await _enrich(draft, own_db)
                await AsyncJobService._finish(async_job.id, enriched.model_dump_json(), None)

        except Exception as exc:
            logger.error("email_generate job %s failed: %s", async_job.id, exc)
            await AsyncJobService._finish(async_job.id, None, str(exc))

    AsyncJobService.run(async_job.id, _work())
    return {"job_id": async_job.id, "status": "pending", "type": "email_generate"}


@router.post("/{email_id}/send", response_model=EmailSendResponse)
async def send_email(
    email_id: str,
    body: EmailSendRequest,
    db: AsyncSession = Depends(get_db),
) -> EmailSendResponse:
    """Send the email via SMTP or return a mailto: link.

    Rate limits: 5/day, 10 min between same domain, no repeat in 7 days.
    """
    result = await db.execute(
        select(FollowUpEmail).where(FollowUpEmail.id == email_id)
    )
    email = result.scalars().first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    if email.status not in ("draft", "approved"):
        raise HTTPException(status_code=400, detail=f"Email is in status '{email.status}' — cannot send")

    # Apply user overrides
    if body.recipient_email:
        email.recipient_email = body.recipient_email
    if body.subject:
        email.subject = body.subject
    if body.body:
        email.body_plain = body.body

    if body.send_via == "mailto":
        link = _email_sender.generate_mailto_link(email)
        email.status = "sent"
        email.sent_via = "mailto"
        email.sent_at = datetime.utcnow()
        await db.commit()
        return EmailSendResponse(
            success=True,
            message="mailto link generated",
            mailto_link=link,
        )

    elif body.send_via == "smtp":
        try:
            success = await _email_sender.send_smtp(email, db)
        except EmailRateLimitError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc

        if success:
            email.status = "sent"
            email.sent_via = "smtp"
            email.sent_at = datetime.utcnow()
            await db.commit()
            return EmailSendResponse(success=True, message="Email sent successfully")
        else:
            email.status = "failed"
            await db.commit()
            return EmailSendResponse(success=False, message="SMTP send failed — check server logs")

    raise HTTPException(status_code=400, detail="send_via must be 'smtp' or 'mailto'")


@router.post("/{email_id}/skip", response_model=FollowUpEmailRead)
async def skip_email(email_id: str, db: AsyncSession = Depends(get_db)) -> FollowUpEmailRead:
    """Mark email as skipped (user decided not to send)."""
    result = await db.execute(
        select(FollowUpEmail).where(FollowUpEmail.id == email_id)
    )
    email = result.scalars().first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    email.status = "skipped"
    await db.commit()
    await db.refresh(email)
    return await _enrich(email, db)


@router.post("/{email_id}/regenerate", response_model=FollowUpEmailRead)
async def regenerate_email(
    email_id: str,
    db: AsyncSession = Depends(get_db),
    generator: EmailGenerator = Depends(_get_email_generator),
) -> FollowUpEmailRead:
    """Regenerate email with fresh Claude output (same context, different wording)."""
    result = await db.execute(
        select(FollowUpEmail).where(FollowUpEmail.id == email_id)
    )
    email = result.scalars().first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    app_result = await db.execute(
        select(Application).where(Application.id == email.application_id)
    )
    application = app_result.scalars().first()
    if not application or not application.job_id:
        raise HTTPException(status_code=400, detail="Application or job not found")

    job_result = await db.execute(
        select(JobPosting).where(JobPosting.id == application.job_id)
    )
    job = job_result.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    now = datetime.utcnow()
    days_since_applied = (
        (now - application.applied_date).days if application.applied_date
        else (now - application.created_at).days
    )

    try:
        if email.email_type == "post_application":
            generated = await generator.generate_post_application(application, job, days_since_applied)
        elif email.email_type == "post_interview_thankyou":
            interview_result = await db.execute(
                select(InterviewRound)
                .where(
                    InterviewRound.application_id == email.application_id,
                    InterviewRound.status == "completed",
                )
                .order_by(InterviewRound.updated_at.desc())
            )
            interview = interview_result.scalars().first()
            if interview:
                generated = await generator.generate_post_interview_thankyou(application, job, interview)
            else:
                generated = await generator.generate_warm_reengagement(application, job, days_since_applied)
        else:
            generated = await generator.generate_warm_reengagement(application, job, days_since_applied)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Regeneration failed: {exc}") from exc

    email.subject = generated.subject
    email.body_html = generator.render_html(generated)
    email.body_plain = generator.render_plain(generated)
    email.status = "draft"
    await db.commit()
    await db.refresh(email)
    return await _enrich(email, db)
