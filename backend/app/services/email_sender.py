"""Email sending service: SMTP (via aiosmtplib) and mailto link generation.

Rate limits enforced:
- Max 5 emails per day (spam prevention)
- Min 10 minutes between emails to the same domain
- Never email the same recipient twice within 7 days
"""
from __future__ import annotations

import logging
import urllib.parse
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.follow_up_email import FollowUpEmail

logger = logging.getLogger(__name__)


class EmailRateLimitError(Exception):
    """Raised when an email send would violate rate limits."""


class EmailSender:
    """Handles email delivery via SMTP or mailto link generation.

    Attributes:
        max_per_day: Maximum emails allowed per day.
        min_minutes_between_same_domain: Minimum gap between emails to same domain.
        repeat_days: Days before same recipient can be emailed again.
    """

    def __init__(
        self,
        max_per_day: int = 5,
        min_minutes_between_same_domain: int = 10,
        repeat_days: int = 7,
    ) -> None:
        self.max_per_day = max_per_day
        self.min_minutes_between_same_domain = min_minutes_between_same_domain
        self.repeat_days = repeat_days

    async def send_smtp(self, email: FollowUpEmail, db: AsyncSession) -> bool:
        """Send email via SMTP using aiosmtplib.

        Args:
            email: The FollowUpEmail record to send.
            db: Database session for rate limit checks.

        Returns:
            True if sent successfully, False on failure.

        Raises:
            EmailRateLimitError: If rate limits would be exceeded.
        """
        try:
            import aiosmtplib
        except ImportError:
            logger.error("aiosmtplib not installed — cannot send SMTP email")
            return False

        if not settings.SMTP_USER or not settings.SMTP_PASS:
            logger.warning("SMTP credentials not configured — cannot send email")
            return False

        if not email.recipient_email:
            logger.error("No recipient email set for email %s", email.id)
            return False

        await self._check_rate_limits(email.recipient_email, db)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = email.subject
        msg["From"] = f"{self._candidate_name()} <{settings.SMTP_USER}>"
        msg["To"] = email.recipient_email
        if settings.NOTIFICATION_EMAIL:
            msg["Reply-To"] = settings.NOTIFICATION_EMAIL

        msg.attach(MIMEText(email.body_plain, "plain"))
        msg.attach(MIMEText(email.body_html, "html"))

        try:
            await aiosmtplib.send(
                msg,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASS,
                use_tls=True,
            )
            logger.info("Email %s sent via SMTP to %s", email.id, email.recipient_email)
            return True
        except Exception as exc:
            logger.error("Failed to send email %s via SMTP: %s", email.id, exc)
            return False

    def generate_mailto_link(self, email: FollowUpEmail) -> str:
        """Generate a mailto: link that opens the user's default email client.

        Args:
            email: The FollowUpEmail record.

        Returns:
            A mailto: URL string with pre-filled To, Subject, and Body.
        """
        recipient = email.recipient_email or ""
        params = urllib.parse.urlencode(
            {
                "subject": email.subject,
                "body": email.body_plain,
            },
            quote_via=urllib.parse.quote,
        )
        return f"mailto:{urllib.parse.quote(recipient)}?{params}"

    async def _check_rate_limits(
        self, recipient_email: str, db: AsyncSession
    ) -> None:
        """Enforce sending rate limits.

        Args:
            recipient_email: The intended recipient address.
            db: Database session.

        Raises:
            EmailRateLimitError: If any rate limit would be exceeded.
        """
        now = datetime.utcnow()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        domain = recipient_email.split("@")[-1].lower() if "@" in recipient_email else ""

        # Max 5 per day
        stmt = select(FollowUpEmail).where(
            FollowUpEmail.status == "sent",
            FollowUpEmail.sent_at >= day_start,
        )
        result = await db.execute(stmt)
        sent_today = len(result.scalars().all())
        if sent_today >= self.max_per_day:
            raise EmailRateLimitError(
                f"Daily email limit reached ({self.max_per_day}/day). "
                "Try again tomorrow."
            )

        # Min 10 min between emails to same domain
        if domain:
            cutoff = now - timedelta(minutes=self.min_minutes_between_same_domain)
            stmt2 = select(FollowUpEmail).where(
                FollowUpEmail.status == "sent",
                FollowUpEmail.recipient_email.like(f"%@{domain}"),
                FollowUpEmail.sent_at >= cutoff,
            )
            result2 = await db.execute(stmt2)
            recent_domain = result2.scalars().first()
            if recent_domain:
                raise EmailRateLimitError(
                    f"Too soon to email another {domain} address. "
                    f"Wait {self.min_minutes_between_same_domain} minutes between emails to the same domain."
                )

        # No repeat within 7 days
        repeat_cutoff = now - timedelta(days=self.repeat_days)
        stmt3 = select(FollowUpEmail).where(
            FollowUpEmail.status == "sent",
            FollowUpEmail.recipient_email == recipient_email,
            FollowUpEmail.sent_at >= repeat_cutoff,
        )
        result3 = await db.execute(stmt3)
        recent_recipient = result3.scalars().first()
        if recent_recipient:
            raise EmailRateLimitError(
                f"Already emailed {recipient_email} within the last {self.repeat_days} days."
            )

    def _candidate_name(self) -> str:
        """Return candidate display name from profile or fallback."""
        try:
            import json
            from pathlib import Path
            profile_path = Path(__file__).parent.parent / "templates" / "candidate_profile.json"
            if profile_path.exists():
                profile = json.loads(profile_path.read_text())
                return profile.get("personal", {}).get("full_name", "Arvind Soni")
        except Exception:
            pass
        return "Arvind Soni"
