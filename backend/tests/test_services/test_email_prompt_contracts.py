"""Grounding contracts for candidate-facing email prompts."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.email_generator import EmailGenerator


def _job() -> SimpleNamespace:
    return SimpleNamespace(
        id="job-1",
        title="Cloud Architect",
        company="Example Ltd",
        source="direct",
        skills=["AWS"],
    )


def _application() -> SimpleNamespace:
    return SimpleNamespace(
        recruiter_name="Alex",
        agency_name=None,
    )


def _generator(body: str) -> tuple[EmailGenerator, MagicMock]:
    client = MagicMock()
    client.complete_json = AsyncMock(
        return_value={
            "subject": "Cloud Architect",
            "greeting": "Dear Alex,",
            "body": body,
            "sign_off": "Kind regards,",
        }
    )
    generator = EmailGenerator(client)
    generator._profile = {
        "summary": "Cloud architect with 20+ years of experience.",
        "experience": [],
        "skills": [],
        "personal": {"full_name": "Test Candidate"},
    }
    return generator, client


@pytest.mark.asyncio
async def test_email_prompt_uses_runtime_evidence_not_hardcoded_candidate() -> None:
    generator, client = _generator(
        "My 20+ years of cloud architecture experience align with this role."
    )

    email = await generator.generate_post_application(
        _application(),
        _job(),
        days_since_applied=5,
    )

    assert "20+" in email.body
    user_prompt = client.complete_json.await_args.kwargs["user"]
    assert '"prompt_id": "email_post_application"' in user_prompt
    assert "APPROVED_EVIDENCE" in user_prompt
    assert "Arvind Soni" not in user_prompt


@pytest.mark.asyncio
async def test_email_body_is_withheld_when_candidate_number_mutates() -> None:
    generator, _ = _generator(
        "My 30+ years of cloud architecture experience align with this role."
    )

    email = await generator.generate_post_application(
        _application(),
        _job(),
        days_since_applied=5,
    )

    assert email.body == ""
