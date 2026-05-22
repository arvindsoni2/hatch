"""Generates answers to custom application questions using Claude."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Common question patterns that can be answered directly from the candidate
# profile without a Claude API call.
_STANDARD_QUESTION_KEYS: list[tuple[str, str]] = [
    # (lowercase substring to match in question, profile dot-path)
    ("right to work", "standard_answers.right_to_work"),
    ("eligible to work", "standard_answers.right_to_work"),
    ("require sponsorship", "standard_answers.requires_sponsorship"),
    ("notice period", "standard_answers.notice_period"),
    ("earliest start", "standard_answers.availability"),
    ("availability", "standard_answers.availability"),
    ("day rate", "standard_answers.expected_rate"),
    ("expected rate", "standard_answers.expected_rate"),
    ("desired rate", "standard_answers.expected_rate"),
    ("salary expectation", "standard_answers.expected_salary"),
    ("linkedin", "personal.linkedin"),
    ("github", "personal.github"),
]

_SYSTEM_PROMPT = """\
You are writing application answers on behalf of a Solutions Architect with 20+ years of \
experience in UK contract roles. Your tone is CONFIDENT and DIRECT. Keep every answer under \
200 words. Base each answer on the candidate profile and job description provided. \
Do NOT fabricate credentials, companies, or qualifications that are not in the profile."""

_USER_TEMPLATE = """\
Candidate profile summary:
{profile_summary}

Job description:
{job_description}

Answer each of the following application questions. Respond with a JSON object whose keys \
are the exact question strings and values are the answer strings.

Questions:
{questions_json}"""


class CustomQuestionAnswerer:
    """Generates answers for custom application form questions.

    Checks the candidate profile's standard_answers section first to avoid
    unnecessary Claude API calls for common questions (right-to-work, notice
    period, etc.). Only questions that cannot be answered from the profile
    are sent to Claude.
    """

    def __init__(self, claude_client: Any) -> None:
        """Initialise with a ClaudeClient instance.

        Args:
            claude_client: An instance of ClaudeClient from services/claude_client.py.
        """
        self._claude = claude_client

    async def answer_questions(
        self,
        questions: list[str],
        job_description: str,
        profile: dict[str, Any],
    ) -> dict[str, str]:
        """Generate answers for a list of custom application questions.

        Resolves common questions directly from the candidate profile's
        standard_answers section before calling Claude. Only unmapped
        questions are sent to Claude in a single batched call.

        Args:
            questions: List of question strings from the application form.
            job_description: Full text of the job description for context.
            profile: Candidate profile dict.

        Returns:
            Dict mapping each question string to its answer string.
        """
        answers: dict[str, str] = {}
        remaining: list[str] = []

        for question in questions:
            answer = self._lookup_standard(question, profile)
            if answer is not None:
                answers[question] = answer
                logger.debug("Standard answer used for: %s", question[:60])
            else:
                remaining.append(question)

        if remaining:
            claude_answers = await self._ask_claude(remaining, job_description, profile)
            answers.update(claude_answers)

        return answers

    # ---------------------------------------------------------------------- #
    # Private helpers
    # ---------------------------------------------------------------------- #

    def _lookup_standard(self, question: str, profile: dict[str, Any]) -> str | None:
        """Check if a question can be answered from the profile directly.

        Args:
            question: The question text.
            profile: Candidate profile dict.

        Returns:
            Answer string or None.
        """
        q_lower = question.lower()
        for keyword, dot_path in _STANDARD_QUESTION_KEYS:
            if keyword in q_lower:
                value = self._get_nested(profile, dot_path)
                if value:
                    return value
        return None

    async def _ask_claude(
        self,
        questions: list[str],
        job_description: str,
        profile: dict[str, Any],
    ) -> dict[str, str]:
        """Send unanswered questions to Claude in a single batched call.

        Args:
            questions: Questions not resolved from the profile.
            job_description: Job description for context.
            profile: Candidate profile dict.

        Returns:
            Dict of question → answer from Claude.
        """
        import json

        profile_summary = self._build_profile_summary(profile)
        questions_json = json.dumps(questions, indent=2)

        user_msg = _USER_TEMPLATE.format(
            profile_summary=profile_summary,
            job_description=job_description[:3000],  # trim to avoid token bloat
            questions_json=questions_json,
        )

        try:
            result = await self._claude.complete_json(
                system=_SYSTEM_PROMPT,
                user=user_msg,
                max_tokens=2048,
            )
            # Ensure all questions have an answer (default to empty string if missing)
            return {q: str(result.get(q, "")) for q in questions}
        except Exception as exc:
            logger.error("Claude question answering failed: %s", exc)
            return {q: "" for q in questions}

    def _build_profile_summary(self, profile: dict[str, Any]) -> str:
        """Build a concise text summary of the candidate profile for the prompt.

        Args:
            profile: Full candidate profile dict.

        Returns:
            Multi-line summary string.
        """
        personal = profile.get("personal", {})
        employment = profile.get("employment", {})
        compensation = profile.get("compensation", {})
        eligibility = profile.get("eligibility", {})

        lines = [
            f"Name: {personal.get('full_name', '')}",
            f"Email: {personal.get('email', '')}",
            f"Location: {personal.get('city', '')}, {personal.get('country', 'UK')}",
            f"Current role / title: {employment.get('current_title', '')}",
            f"Years experience: {employment.get('years_experience', '')}",
            f"Notice period: {employment.get('notice_period', '')}",
            f"Availability: {employment.get('availability', '')}",
            f"Expected day rate: {compensation.get('expected_rate', '')}",
            f"Right to work in UK: {eligibility.get('right_to_work', 'Yes')}",
            f"Requires sponsorship: {eligibility.get('requires_sponsorship', 'No')}",
            f"Key skills: {', '.join(profile.get('skills', [])[:15])}",
        ]
        return "\n".join(line for line in lines if line.split(": ", 1)[-1])

    def _get_nested(self, data: dict[str, Any], dot_path: str) -> str | None:
        """Walk a dot-separated path into a nested dict.

        Args:
            data: Nested dict.
            dot_path: E.g. "standard_answers.right_to_work".

        Returns:
            String value or None.
        """
        parts = dot_path.split(".")
        current: Any = data
        for part in parts:
            if not isinstance(current, dict):
                return None
            current = current.get(part)
            if current is None:
                return None
        return str(current) if current is not None else None
