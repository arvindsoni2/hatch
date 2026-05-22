"""Recruiter contact finder — extracts contact info from job listings and drafts outreach."""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.job import JobPosting
from ..models.recruiter import RecruiterContact

if TYPE_CHECKING:
    from .claude_client import ClaudeClient

logger = logging.getLogger(__name__)

# Common email pattern guesses for a given name + company domain
_EMAIL_PATTERNS = [
    "{first}.{last}@{domain}",
    "{first}{last}@{domain}",
    "{f}{last}@{domain}",
    "{first}@{domain}",
]


def _extract_domain_from_company(company_name: str) -> str | None:
    """Guess a company's email domain from its name.

    Args:
        company_name: Raw company name string.

    Returns:
        Guessed domain string (e.g. 'acme.com'), or None if too ambiguous.
    """
    if not company_name:
        return None
    # Strip Ltd, plc, Inc etc. and lowercase
    cleaned = re.sub(
        r"\b(ltd|limited|plc|inc|llc|gmbh|group|uk|solutions|consulting|services|technology|technologies)\b",
        "",
        company_name.lower(),
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"[^a-z0-9]+", "", cleaned).strip()
    if len(cleaned) < 3:
        return None
    return f"{cleaned}.com"


def _parse_name_from_text(text: str) -> tuple[str | None, str | None]:
    """Try to extract a recruiter/contact name from job listing text.

    Looks for phrases like 'Contact John Smith', 'Recruiter: Jane Doe', etc.

    Args:
        text: Job description text.

    Returns:
        Tuple of (first_name, last_name) or (None, None).
    """
    if not text:
        return None, None

    patterns = [
        r"(?:contact|recruiter|consultant|manager)[:\s]+([A-Z][a-z]+)\s+([A-Z][a-z]+)",
        r"(?:please contact|speak to|ask for)[:\s]+([A-Z][a-z]+)\s+([A-Z][a-z]+)",
        r"(?:hiring manager)[:\s]+([A-Z][a-z]+)\s+([A-Z][a-z]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1), match.group(2)
    return None, None


def _guess_emails(first: str, last: str, domain: str) -> list[tuple[str, float]]:
    """Generate plausible email guesses with confidence scores.

    Args:
        first: First name (lowercase).
        last: Last name (lowercase).
        domain: Company email domain.

    Returns:
        List of (email, confidence) tuples sorted by confidence desc.
    """
    f = first[0] if first else ""
    guesses = [
        (p.format(first=first, last=last, f=f, domain=domain), confidence)
        for p, confidence in zip(
            _EMAIL_PATTERNS,
            [0.70, 0.65, 0.55, 0.45],
        )
    ]
    return guesses


class RecruiterFinderService:
    """Finds recruiter contacts from job listings and drafts outreach messages."""

    def __init__(self, claude_client: ClaudeClient) -> None:
        self._client = claude_client

    async def find_recruiter(self, job: JobPosting) -> RecruiterContact | None:
        """Parse recruiter contact info from a job listing.

        Args:
            job: The JobPosting ORM object.

        Returns:
            An unsaved RecruiterContact model, or None if no contact info found.
        """
        text = f"{job.title or ''} {job.description or ''}"
        first, last = _parse_name_from_text(text)

        if not first or not last:
            # Can't determine contact name — still create a skeleton record
            if not job.company:
                return None
            return RecruiterContact(
                job_id=job.id,
                company_name=job.company,
                outreach_status="not_sent",
            )

        domain = _extract_domain_from_company(job.company or "")
        email_guess: str | None = None
        email_confidence: float | None = None

        if domain:
            guesses = _guess_emails(first.lower(), last.lower(), domain)
            if guesses:
                email_guess, email_confidence = guesses[0]

        return RecruiterContact(
            job_id=job.id,
            company_name=job.company,
            recruiter_name=f"{first} {last}",
            email_guess=email_guess,
            email_confidence=email_confidence,
            outreach_status="draft",
        )

    async def draft_outreach(
        self,
        contact: RecruiterContact,
        job: JobPosting,
        profile: dict,
    ) -> str:
        """Generate a personalised LinkedIn connection / outreach message.

        Args:
            contact: The RecruiterContact to address.
            job: The related JobPosting.
            profile: Candidate profile dict (from candidate_profile.json).

        Returns:
            Outreach message text (under 150 words, confident & direct tone).
        """
        name = contact.recruiter_name or "the hiring team"
        role = job.title or "this role"
        company = job.company or "your organisation"
        about = profile.get("standard_answers", {}).get(
            "about_yourself_short",
            "Solutions Architect with 20+ years' experience.",
        )

        system = (
            "You are a professional writing concise, confident, direct LinkedIn outreach messages. "
            "Tone: confident, no filler words, no hollow phrases like 'I hope this message finds you well'. "
            "Be direct and specific. Maximum 150 words."
        )
        user = (
            f"Write a short LinkedIn connection request or InMail message from a candidate to {name} at {company}. "
            f"The candidate is applying for the role: {role}. "
            f"Candidate background: {about}. "
            f"Mention the specific role and one relevant credential. End with a clear ask (e.g. 'happy to connect if you'd like to discuss'). "
            f"Under 150 words."
        )

        try:
            message = await self._client.complete(system=system, user=user, max_tokens=300)
            return message.strip()
        except Exception as exc:
            logger.error("Outreach draft failed: %s", exc)
            return (
                f"Hi {name},\n\nI noticed the {role} opportunity at {company} and believe my background "
                f"as a Solutions Architect with 20+ years' experience is a strong fit. "
                f"Happy to connect if you'd like to discuss.\n\nBest regards"
            )

    async def save_contact(self, contact: RecruiterContact, db: AsyncSession) -> RecruiterContact:
        """Persist a RecruiterContact record.

        Args:
            contact: RecruiterContact ORM object (unsaved).
            db: Async SQLAlchemy session.

        Returns:
            The saved RecruiterContact with ID populated.
        """
        db.add(contact)
        await db.flush()
        await db.refresh(contact)
        return contact
