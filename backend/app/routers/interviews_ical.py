"""iCalendar (.ics) export for interview rounds."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.application import Application, InterviewRound
from ..models.job import JobPosting

router = APIRouter(prefix="/api/v2/interviews", tags=["interviews"])


@router.get("/{interview_id}/ical", response_class=Response)
async def download_interview_ical(
    interview_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Return a .ics calendar file for the given interview round.

    Includes the interview title, location, interviewer, and a 1-hour block
    by default (overridden by duration_minutes if set).
    """
    from icalendar import Calendar, Event  # noqa: PLC0415

    result = await db.execute(
        select(InterviewRound).where(InterviewRound.id == interview_id)
    )
    interview = result.scalar_one_or_none()
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")

    if not interview.scheduled_at:
        raise HTTPException(
            status_code=422,
            detail="Interview has no scheduled date — set a date before exporting to calendar.",
        )

    # Try to fetch job title + company via Application → JobPosting
    job_title: str | None = None
    company: str | None = None
    try:
        app_result = await db.execute(
            select(Application).where(Application.id == interview.application_id)
        )
        app = app_result.scalar_one_or_none()
        if app and app.job_id:
            job_result = await db.execute(
                select(JobPosting).where(JobPosting.id == app.job_id)
            )
            job = job_result.scalar_one_or_none()
            if job:
                job_title = job.title
                company = job.company
    except Exception:
        pass  # fallback to generic title

    # Build .ics
    cal = Calendar()
    cal.add("prodid", "-//JobPilot//Interview Export//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")

    ev = Event()
    summary = _build_summary(interview, job_title, company)
    ev.add("summary", summary)

    dtstart = _ensure_aware(interview.scheduled_at)
    duration = timedelta(minutes=interview.duration_minutes or 60)
    ev.add("dtstart", dtstart)
    ev.add("dtend", dtstart + duration)
    ev.add("dtstamp", datetime.now(tz=timezone.utc))
    ev.add("uid", f"jobpilot-interview-{interview_id}@jobpilot.local")

    if interview.location:
        ev.add("location", interview.location)

    description_parts: list[str] = []
    if interview.interviewer_name:
        description_parts.append(f"Interviewer: {interview.interviewer_name}")
    if interview.type:
        description_parts.append(f"Type: {interview.type}")
    if interview.prep_notes:
        description_parts.append(f"\nPrep notes:\n{interview.prep_notes}")
    if description_parts:
        ev.add("description", "\n".join(description_parts))

    cal.add_component(ev)

    ics_bytes = cal.to_ical()
    filename = f"interview_{interview_id}.ics"
    return Response(
        content=ics_bytes,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _build_summary(
    interview: Any,
    job_title: str | None,
    company: str | None,
) -> str:
    """Build a human-readable event title."""
    round_label = f"Round {interview.round_number}" if interview.round_number else "Interview"
    type_label = f" ({interview.type})" if interview.type else ""
    if job_title and company:
        return f"{round_label}{type_label}: {job_title} @ {company}"
    if job_title:
        return f"{round_label}{type_label}: {job_title}"
    if company:
        return f"{round_label}{type_label} @ {company}"
    return f"{round_label}{type_label}"


def _ensure_aware(dt: datetime) -> datetime:
    """Attach UTC timezone if the datetime is naive."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
