"""Tests for CoverLetterGenerator — word count, keywords, paragraph regeneration."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.tailor import (
    ATSKeywords,
    CoverLetterResult,
    JDAnalysisResult,
    TailoredCVResult,
    TailoredExperience,
)
from app.services.cl_generator import CoverLetterGenerator, _parse_cover_letter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PERSONAL = {
    "full_name": "Arvind Soni",
    "email": "arvind@example.com",
    "phone": "+44 7000 000000",
    "location": "United Kingdom",
}

JD_ANALYSIS = JDAnalysisResult(
    role_title="Solutions Architect",
    ats_keywords=ATSKeywords(
        technical=["AWS", "Terraform", "GenAI"],
        methodologies=["TOGAF"],
        soft_skills=[],
        domain=["energy"],
        certifications=[],
    ),
)

TAILORED_CV = TailoredCVResult(
    summary="Solutions Architect with 20+ years...",
    skills=[],
    experience=[
        TailoredExperience(
            role="Solutions Architect",
            company="Company A",
            period="2022–Present",
            achievements=["Led cloud migration saving £500K."],
        )
    ],
    certifications=["PMP"],
)

SHORT_CL_RESPONSE = {
    "subject_line": "Solutions Architect — Outside IR35",
    "greeting": "Dear Hiring Manager,",
    "body_paragraphs": [
        "I am writing to express my strong interest in the Solutions Architect position.",
        "With 20+ years of experience delivering enterprise-scale AWS and Terraform architectures, I bring a proven track record.",
        "My expertise in GenAI and TOGAF aligns closely with your requirements for cloud transformation leadership.",
        "I welcome the opportunity to discuss how my experience can contribute to your programme.",
    ],
    "sign_off": "Yours sincerely,",
    "word_count": 62,
    "key_keywords_used": ["AWS", "Terraform", "GenAI", "TOGAF"],
}

LONG_CL_RESPONSE = {
    **SHORT_CL_RESPONSE,
    "body_paragraphs": [
        " ".join(["word"] * 100),
        " ".join(["word"] * 100),
        " ".join(["word"] * 100),
        " ".join(["word"] * 100),
    ],
    "word_count": 400,
}


def make_mock_client(response_dict: dict) -> MagicMock:
    client = MagicMock()
    client.complete_json = AsyncMock(return_value=response_dict)
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_returns_cover_letter():
    client = make_mock_client(SHORT_CL_RESPONSE)
    gen = CoverLetterGenerator(client)
    result = await gen.generate(JD_ANALYSIS, TAILORED_CV, PERSONAL)

    assert isinstance(result, CoverLetterResult)
    assert result.subject_line != ""
    assert len(result.body_paragraphs) == 4
    assert result.word_count > 0
    assert result.generation_provenance is not None
    assert result.generation_provenance.prompt_metadata.prompt_version == "2.0.0"
    assert "generation_provenance" not in result.model_dump()


@pytest.mark.asyncio
async def test_word_count_within_range():
    client = make_mock_client(SHORT_CL_RESPONSE)
    gen = CoverLetterGenerator(client)
    result = await gen.generate(JD_ANALYSIS, TAILORED_CV, PERSONAL)

    # 62 words is below max — should not trigger trim
    assert result.word_count <= 350
    # Should only call complete_json once (no trim retry)
    assert client.complete_json.call_count == 1


@pytest.mark.asyncio
async def test_long_letter_triggers_trim_retry():
    """A letter > 350 words should trigger a second Claude call."""
    # First call returns too-long, second call returns short
    client = MagicMock()
    client.complete_json = AsyncMock(side_effect=[LONG_CL_RESPONSE, SHORT_CL_RESPONSE])
    gen = CoverLetterGenerator(client)

    result = await gen.generate(JD_ANALYSIS, TAILORED_CV, PERSONAL)

    # Should have called twice (initial + trim retry)
    assert client.complete_json.call_count == 2
    assert result.word_count <= 350


@pytest.mark.asyncio
async def test_jd_keywords_present_in_result():
    client = make_mock_client(SHORT_CL_RESPONSE)
    gen = CoverLetterGenerator(client)
    result = await gen.generate(JD_ANALYSIS, TAILORED_CV, PERSONAL)

    assert "AWS" in result.key_keywords_used


@pytest.mark.asyncio
async def test_cover_letter_flags_unsupported_metric():
    response = {
        **SHORT_CL_RESPONSE,
        "body_paragraphs": [
            "I reduced platform costs by 99% while delivering AWS architecture.",
            "I can bring that delivery focus to your programme.",
        ],
        "word_count": 18,
    }
    client = make_mock_client(response)
    gen = CoverLetterGenerator(client)

    result = await gen.generate(JD_ANALYSIS, TAILORED_CV, PERSONAL)

    assert result.grounding_issues
    assert "99%" in result.grounding_issues[0]


@pytest.mark.asyncio
async def test_regenerate_paragraph():
    client = make_mock_client({"paragraph": "Rewritten paragraph with AWS and Terraform focus."})
    gen = CoverLetterGenerator(client)

    current = CoverLetterResult(
        subject_line="Test",
        greeting="Dear Hiring Manager,",
        body_paragraphs=["Para 1", "Para 2", "Para 3", "Para 4"],
        sign_off="Sincerely,",
        word_count=8,
        key_keywords_used=[],
    )

    result = await gen.regenerate_paragraph(1, "Focus more on AWS experience", current, JD_ANALYSIS)

    assert result.body_paragraphs[1] == "Rewritten paragraph with AWS and Terraform focus."
    assert result.body_paragraphs[0] == "Para 1"  # Other paragraphs unchanged


@pytest.mark.asyncio
async def test_regenerate_paragraph_cannot_bypass_numeric_fidelity():
    client = make_mock_client({"paragraph": "Managed 120 locations."})
    gen = CoverLetterGenerator(client)
    current = CoverLetterResult(
        subject_line="Test",
        greeting="Dear Hiring Manager,",
        body_paragraphs=[
            "Managed 120+ locations.",
            "Delivered safely.",
        ],
        sign_off="Sincerely,",
        word_count=5,
    )

    result = await gen.regenerate_paragraph(
        0,
        "Rephrase this paragraph",
        current,
        JD_ANALYSIS,
    )

    assert any("120 locations" in issue for issue in result.grounding_issues)
    assert result.generation_provenance is not None
    assert (
        result.generation_provenance.prompt_metadata.prompt_id
        == "cover_letter_paragraph_regeneration"
    )
    prompt = " ".join(str(arg) for arg in client.complete_json.call_args.args)
    assert "SHARED FACTUALITY CONTRACT (v1.0.0)" in prompt
    assert "SHARED NUMERIC-FIDELITY CONTRACT (v1.0.0)" in prompt


def test_parse_cover_letter():
    result = _parse_cover_letter(SHORT_CL_RESPONSE)
    assert result.subject_line == "Solutions Architect — Outside IR35"
    assert len(result.body_paragraphs) == 4
    assert result.word_count == 62
