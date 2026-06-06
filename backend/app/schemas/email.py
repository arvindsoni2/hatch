"""Pydantic schemas for follow-up email generation, sending, and reading."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class GeneratedEmail(BaseModel):
    """Structured output from Claude email generation."""

    email_type: str
    subject: str
    greeting: str
    body: str
    sign_off: str


class FollowUpEmailRead(BaseModel):
    """Full follow-up email record returned to the frontend."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    application_id: str
    follow_up_id: Optional[str] = None
    email_type: str
    recipient_email: Optional[str] = None
    recipient_name: Optional[str] = None
    subject: str
    body_html: str
    body_plain: str
    status: str
    sent_via: Optional[str] = None
    sent_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    created_at: datetime
    # Denormalised job context for display
    job_title: Optional[str] = None
    company: Optional[str] = None


class FollowUpEmailListItem(BaseModel):
    """Lightweight summary for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    application_id: str
    email_type: str
    recipient_email: Optional[str] = None
    subject: str
    status: str
    created_at: datetime
    job_title: Optional[str] = None
    company: Optional[str] = None


class EmailGenerateRequest(BaseModel):
    """Request body for POST /api/emails/generate/{application_id}."""

    email_type: str
    # 'post_application' | 'post_interview_thankyou' | 'warm_reengagement' | 'custom'


class EmailUpdateRequest(BaseModel):
    """Request body for PATCH /api/emails/{email_id}."""

    subject: Optional[str] = None
    body: Optional[str] = None
    recipient_email: Optional[str] = None
    recipient_name: Optional[str] = None


class EmailSendRequest(BaseModel):
    """Request body for POST /api/emails/{email_id}/send."""

    send_via: str  # 'smtp' | 'mailto'
    recipient_email: str
    subject: Optional[str] = None  # override if user edited
    body: Optional[str] = None     # override if user edited


class EmailSendResponse(BaseModel):
    """Response from POST /api/emails/{email_id}/send."""

    success: bool
    message: str
    mailto_link: Optional[str] = None  # populated when send_via='mailto'


class EmailStats(BaseModel):
    """Summary statistics for sent emails."""

    sent_this_week: int = 0
    sent_total: int = 0
    pending_drafts: int = 0
    by_type: dict[str, int] = {}
    # e.g. {'post_application': 3, 'post_interview_thankyou': 2}
