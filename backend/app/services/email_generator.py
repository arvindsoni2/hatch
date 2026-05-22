"""Claude-powered follow-up email drafting service.

Generates three types of emails:
- post_application: 5 business days after applying
- post_interview_thankyou: within 24h of interview completion
- warm_reengagement: 14+ days with no response

All emails are under 120 words, professional tone, no generic phrases.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from ..models.application import Application, InterviewRound
from ..models.follow_up_email import FollowUpEmail
from ..models.job import JobPosting
from ..schemas.email import GeneratedEmail
from .claude_client import ClaudeClient

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "emails"

# Candidate details loaded from profile
_CANDIDATE_PROFILE_PATH = Path(__file__).parent.parent / "templates" / "candidate_profile.json"

_BANNED_PHRASES = (
    "I hope this email finds you well",
    "I am writing to follow up",
    "I hope you're well",
    "passionate about",
    "excited to",
    "I believe I would be",
    "I wanted to reach out",
    "touch base",
)


def _load_profile() -> dict:
    if _CANDIDATE_PROFILE_PATH.exists():
        return json.loads(_CANDIDATE_PROFILE_PATH.read_text())
    return {}


class EmailGenerator:
    """Generates personalised recruiter emails using Claude.

    Attributes:
        claude: ClaudeClient instance for API calls.
    """

    def __init__(self, claude_client: ClaudeClient) -> None:
        self.claude = claude_client
        self._jinja = Environment(
            loader=FileSystemLoader(str(_TEMPLATES_DIR)),
            autoescape=False,
        )
        self._profile = _load_profile()

    async def generate_post_application(
        self,
        application: Application,
        job: JobPosting,
        days_since_applied: int,
    ) -> GeneratedEmail:
        """Generate a follow-up email 5-7 days after applying.

        Args:
            application: The application record.
            job: The associated job posting.
            days_since_applied: How many days since the application was submitted.

        Returns:
            GeneratedEmail with subject, greeting, body, sign_off.
        """
        recruiter = application.recruiter_name or "Hiring Manager"
        top_skills = self._extract_top_skills(job, 3)
        agency = application.agency_name or ""

        prompt = f"""Write a follow-up email for a job application.

CONTEXT:
- Role: {job.title}
- Company: {job.company or 'the company'}
- Applied: {days_since_applied} days ago
- Recruiter/Contact: {recruiter}
- Agency: {agency or 'N/A'}
- Candidate: Arvind Soni, 20+ years Solutions Architect / Product Owner
- Candidate skills matching this role: {top_skills}
- Application source: {job.source or 'direct'}

RULES:
- Under 120 words total for the body
- Open with a specific reference to the role title and company (not 'I recently applied to a position')
- Include ONE specific achievement that maps to their likely requirements
- Close with a soft call-to-action (available for a call, happy to provide more info)
- Do NOT use any of these phrases: {', '.join(f'"{p}"' for p in _BANNED_PHRASES)}
- Sound like a senior professional, not a graduate
- If recruiter name is known, use 'Dear [name]', otherwise 'Dear Hiring Manager'
- Subject line: concise, references the role

Return valid JSON only:
{{
  "subject": "email subject line",
  "greeting": "Dear ...",
  "body": "the email body (no greeting or sign-off, under 120 words)",
  "sign_off": "Kind regards,"
}}"""

        result = await self.claude.complete_json(
            system="You are a UK recruitment email writer specialising in senior technology roles. "
                   "Write concise, professional follow-up emails. Return only valid JSON.",
            user=prompt,
        )

        email = GeneratedEmail(
            email_type="post_application",
            subject=result.get("subject", f"Following up — {job.title}"),
            greeting=result.get("greeting", f"Dear {recruiter},"),
            body=result.get("body", ""),
            sign_off=result.get("sign_off", "Kind regards,"),
        )
        logger.info("Generated post_application email for job %s", job.id)
        return email

    async def generate_post_interview_thankyou(
        self,
        application: Application,
        job: JobPosting,
        interview: InterviewRound,
    ) -> GeneratedEmail:
        """Generate a thank-you email within 24h of interview completion.

        Args:
            application: The application record.
            job: The associated job posting.
            interview: The completed interview round.

        Returns:
            GeneratedEmail with subject, greeting, body, sign_off.
        """
        interviewer = interview.interviewer_name or "the interview panel"
        recruiter = application.recruiter_name or interviewer
        prep_context = (interview.prep_notes or "")[:300]
        questions_context = ""
        if interview.questions_asked:
            qs = interview.questions_asked
            if isinstance(qs, list):
                questions_context = "; ".join(str(q) for q in qs[:3])
        feedback_context = (interview.feedback or "")[:200]

        prompt = f"""Write a post-interview thank-you email.

CONTEXT:
- Role: {job.title} at {job.company or 'the company'}
- Interview type: {interview.type} (round {interview.round_number})
- Interviewer: {interviewer}
- Interview date: {interview.scheduled_at.strftime('%d %B %Y') if interview.scheduled_at else 'recently'}
- Candidate prep notes: {prep_context or 'N/A'}
- Topics/questions discussed: {questions_context or 'N/A'}
- Post-interview feedback: {feedback_context or 'N/A'}

RULES:
- Under 100 words total for the body
- Reference something specific from the interview context if available
  (if no context, keep general but specific to the role)
- Reinforce ONE key strength relevant to the role
- Express genuine interest in next steps without being sycophantic
- Professional but warm tone — senior consultant, not eager graduate
- Do NOT use: {', '.join(f'"{p}"' for p in _BANNED_PHRASES)}

Return valid JSON only:
{{
  "subject": "Thank you — {job.title} interview",
  "greeting": "Dear {recruiter},",
  "body": "the email body (no greeting or sign-off, under 100 words)",
  "sign_off": "Kind regards,"
}}"""

        result = await self.claude.complete_json(
            system="You are a UK recruitment email writer. Write concise post-interview thank-you emails. Return only valid JSON.",
            user=prompt,
        )

        email = GeneratedEmail(
            email_type="post_interview_thankyou",
            subject=result.get("subject", f"Thank you — {job.title} interview"),
            greeting=result.get("greeting", f"Dear {recruiter},"),
            body=result.get("body", ""),
            sign_off=result.get("sign_off", "Kind regards,"),
        )
        logger.info("Generated post_interview_thankyou email for job %s", job.id)
        return email

    async def generate_warm_reengagement(
        self,
        application: Application,
        job: JobPosting,
        days_since_last_contact: int,
    ) -> GeneratedEmail:
        """Generate a warm re-engagement email after 14+ days with no response.

        Args:
            application: The application record.
            job: The associated job posting.
            days_since_last_contact: Days since last contact or application.

        Returns:
            GeneratedEmail with subject, greeting, body, sign_off.
        """
        recruiter = application.recruiter_name or "Hiring Manager"

        prompt = f"""Write a warm re-engagement email for a job application with no response.

CONTEXT:
- Role: {job.title} at {job.company or 'the company'}
- Applied {days_since_last_contact} days ago with no response
- Recruiter/Contact: {recruiter}
- Candidate value: 20+ years Solutions Architect / Product Owner, Energy, Financial Services, Aviation

RULES:
- Under 80 words total for the body
- NOT pushy or passive-aggressive
- Acknowledge they may be busy or the role may have moved on
- Brief restatement of fit (one sentence)
- Offer graceful out: if the role is filled, are there other opportunities?
- End with a clear but soft CTA
- Do NOT use: {', '.join(f'"{p}"' for p in _BANNED_PHRASES)}

Return valid JSON only:
{{
  "subject": "email subject",
  "greeting": "Dear {recruiter},",
  "body": "the email body (no greeting or sign-off, under 80 words)",
  "sign_off": "Kind regards,"
}}"""

        result = await self.claude.complete_json(
            system="You are a UK recruitment email writer. Write brief, professional re-engagement emails. Return only valid JSON.",
            user=prompt,
        )

        email = GeneratedEmail(
            email_type="warm_reengagement",
            subject=result.get("subject", f"Re: {job.title} application"),
            greeting=result.get("greeting", f"Dear {recruiter},"),
            body=result.get("body", ""),
            sign_off=result.get("sign_off", "Kind regards,"),
        )
        logger.info("Generated warm_reengagement email for job %s", job.id)
        return email

    def render_html(self, email: GeneratedEmail) -> str:
        """Render the HTML email using the wrapper template.

        Args:
            email: Generated email content from Claude.

        Returns:
            Full HTML string ready for sending.
        """
        profile = self._profile
        personal = profile.get("personal", {})
        links = profile.get("professional_links", {})

        template = self._jinja.get_template("follow_up_email_wrapper.html")
        return template.render(
            subject=email.subject,
            greeting=email.greeting,
            body=email.body,
            sign_off=email.sign_off,
            candidate_name=personal.get("full_name", "Arvind Soni"),
            candidate_email=personal.get("email", ""),
            candidate_phone=personal.get("phone", ""),
            linkedin_url=links.get("linkedin_url", ""),
            portfolio_url=links.get("portfolio_url", ""),
        )

    def render_plain(self, email: GeneratedEmail) -> str:
        """Render the plain text email using the Jinja2 plain template.

        Args:
            email: Generated email content from Claude.

        Returns:
            Plain text string ready for use as fallback.
        """
        profile = self._profile
        personal = profile.get("personal", {})
        links = profile.get("professional_links", {})

        template = self._jinja.get_template("follow_up_email_plain.j2")
        return template.render(
            greeting=email.greeting,
            body=email.body,
            sign_off=email.sign_off,
            candidate_name=personal.get("full_name", "Arvind Soni"),
            candidate_email=personal.get("email", ""),
            candidate_phone=personal.get("phone", ""),
            linkedin_url=links.get("linkedin_url", ""),
            portfolio_url=links.get("portfolio_url", ""),
        )

    def save_draft(
        self,
        email: GeneratedEmail,
        application: Application,
        generation_params: dict,
        follow_up_id: str | None = None,
    ) -> FollowUpEmail:
        """Build a FollowUpEmail ORM instance (not yet committed to DB).

        Args:
            email: Generated email content.
            application: The application this email relates to.
            generation_params: Dict of prompt inputs for audit trail.
            follow_up_id: Optional FK to the triggering FollowUp record.

        Returns:
            Unsaved FollowUpEmail ORM instance.
        """
        body_html = self.render_html(email)
        body_plain = self.render_plain(email)

        # Prefill recipient from application if available
        recipient_email = application.recruiter_email
        recipient_name = application.recruiter_name

        return FollowUpEmail(
            follow_up_id=follow_up_id,
            application_id=application.id,
            email_type=email.email_type,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            subject=email.subject,
            body_html=body_html,
            body_plain=body_plain,
            status="draft",
            generation_params=json.dumps(generation_params),
        )

    def _extract_top_skills(self, job: JobPosting, count: int) -> str:
        """Extract top N skills from the job posting.

        Args:
            job: The job posting.
            count: Maximum number of skills to return.

        Returns:
            Comma-separated skill string.
        """
        if job.skills:
            skills = job.skills if isinstance(job.skills, list) else []
            return ", ".join(str(s) for s in skills[:count])
        return "cloud architecture, agile delivery, stakeholder management"
