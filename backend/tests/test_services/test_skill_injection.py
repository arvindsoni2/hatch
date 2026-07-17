"""Guard: SKILL.md instructions must be injected into CV, CL, and ATS generation prompts.

SkillLoader.instructions() exists and is called by each service, but that text
must actually reach the LLM call.  If a service doesn't pass skill_instructions
to render_prompt, the guidance is dead documentation.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.tailor import JDAnalysisResult, TailoredCVResult
from app.services.writing_contracts import (
    SHARED_FACTUALITY_CONTRACT,
    SHARED_NUMERIC_FIDELITY_CONTRACT,
)

_SENTINEL_CV = "flag it as a gap rather than inserting it"
_SENTINEL_CL = "use the company name verbatim in paragraph one"
_SENTINEL_ATS = "suggestions must be grounded in existing master-CV evidence"

_SIMPLE_JD = JDAnalysisResult(role_title="Test Role")
_SIMPLE_CV = TailoredCVResult(summary="Summary", skills=[], experience=[], certifications=[])
_SIMPLE_PERSONAL = {"name": "Test User", "email": "test@example.com"}

_SIMPLE_CV_RAW = {
    "summary": "A summary",
    "skills": [],
    "experience": [],
    "certifications": [],
    "ats_keywords_embedded": [],
    "tailoring_notes": "",
}
_SIMPLE_CL_RAW = {
    "subject_line": "Application: Test",
    "greeting": "Dear Hiring Manager,",
    "body_paragraphs": ["Para 1", "Para 2", "Para 3", "Para 4"],
    "sign_off": "Kind regards,",
    "word_count": 8,
    "key_keywords_used": [],
    "tailoring_notes": "",
}
_SIMPLE_ATS_RAW = {
    "overall_score": 75,
    "keyword_matches": [],
    "format_warnings": [],
    "missing_critical": [],
    "improvement_suggestions": [],
}


def _make_loader(skill_name: str, text: str) -> MagicMock:
    loader = MagicMock()
    loader.instructions = MagicMock(side_effect=lambda name: text if name == skill_name else "")
    return loader


def _captured_prompt(mock_client: MagicMock) -> str:
    """Return the full prompt text passed to the first complete_json call."""
    call = mock_client.complete_json.call_args
    # complete_json(system_prompt, user_prompt, ...)
    return " ".join(str(a) for a in call.args)


# ---------------------------------------------------------------------------
# CV Tailor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cv_prompt_contains_skill_guidance():
    """CVTailor must inject cv-tailoring SKILL.md guidance into the rendered prompt."""
    from app.services.cv_tailor import CVTailor

    mock_client = MagicMock()
    mock_client.complete_json = AsyncMock(return_value=_SIMPLE_CV_RAW)
    loader = _make_loader("cv-tailoring", _SENTINEL_CV)

    tailor = CVTailor(mock_client, skill_loader=loader)
    with patch.object(
        tailor, "_load_master_cv",
        return_value={"summary_variants": {}, "experience": [], "skills": {}},
    ):
        await tailor.tailor(_SIMPLE_JD)

    prompt = _captured_prompt(mock_client)
    assert _SENTINEL_CV in prompt, (
        "cv-tailoring SKILL.md guidance not found in the CV tailoring prompt. "
        "Pass skill_instructions to render_prompt."
    )
    assert SHARED_FACTUALITY_CONTRACT in prompt
    assert SHARED_NUMERIC_FIDELITY_CONTRACT in prompt
    assert "APPROVED_EVIDENCE" in prompt


# ---------------------------------------------------------------------------
# Cover Letter Generator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cl_prompt_contains_skill_guidance():
    """CoverLetterGenerator must inject cover-letter SKILL.md guidance."""
    from app.services.cl_generator import CoverLetterGenerator

    mock_client = MagicMock()
    mock_client.complete_json = AsyncMock(return_value=_SIMPLE_CL_RAW)
    loader = _make_loader("cover-letter", _SENTINEL_CL)

    generator = CoverLetterGenerator(mock_client, skill_loader=loader)
    await generator.generate(_SIMPLE_JD, _SIMPLE_CV, _SIMPLE_PERSONAL)

    prompt = _captured_prompt(mock_client)
    assert _SENTINEL_CL in prompt, (
        "cover-letter SKILL.md guidance not found in the CL generation prompt."
    )
    assert SHARED_FACTUALITY_CONTRACT in prompt
    assert SHARED_NUMERIC_FIDELITY_CONTRACT in prompt
    assert "APPROVED_EVIDENCE" in prompt


# ---------------------------------------------------------------------------
# ATS Optimiser
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ats_prompt_contains_skill_guidance():
    """ATSOptimiser must inject ats-optimization SKILL.md guidance."""
    from app.services.ats_optimiser import ATSOptimiser

    mock_client = MagicMock()
    mock_client.complete_json = AsyncMock(return_value=_SIMPLE_ATS_RAW)
    loader = _make_loader("ats-optimization", _SENTINEL_ATS)

    optimiser = ATSOptimiser(mock_client, skill_loader=loader)
    await optimiser.score("CV content here", _SIMPLE_JD)

    prompt = _captured_prompt(mock_client)
    assert _SENTINEL_ATS in prompt, (
        "ats-optimization SKILL.md guidance not found in the ATS scoring prompt."
    )


# ---------------------------------------------------------------------------
# Missing skill returns empty string (defensive)
# ---------------------------------------------------------------------------

def test_missing_skill_returns_empty_string():
    """SkillLoader.instructions() for an unknown skill name returns '' — never raises."""
    from app.skills.skill_loader import SkillLoader, SkillRegistry
    from pathlib import Path

    registry = SkillRegistry(Path("/nonexistent/skills/dir"))
    loader = SkillLoader(registry)
    result = loader.instructions("no-such-skill")
    assert result == ""
