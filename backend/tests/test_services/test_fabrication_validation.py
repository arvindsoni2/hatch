"""Tests for broadened post-generation fabrication/placeholder validation.

_validate_no_fabrication now returns (blocking, advisory) and scans:
  - blocking: placeholder tokens in summary, skills.items, certifications,
    experience role/company headers
  - advisory: fuzzy achievement mismatch (pre-existing check, now includes summary)

The result.blocking_issues field is populated and surfaced to the API.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.tailor import JDAnalysisResult, TailoredCVResult, TailoredExperience


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_clean_result() -> TailoredCVResult:
    return TailoredCVResult(
        summary="Delivered £500K cost reduction via cloud architecture at Northern Powergrid.",
        skills=[{"category": "Cloud", "items": ["AWS", "Terraform"]}],
        experience=[
            TailoredExperience(
                role="Senior Architect",
                company="Acme Corp",
                period="2021–2024",
                achievements=["Led cloud migration saving £200K annually via platform consolidation."],
            )
        ],
        certifications=["AWS Solutions Architect"],
    )


def _make_placeholder_result() -> TailoredCVResult:
    return TailoredCVResult(
        summary="Led delivery at [Company Name], achieving significant results.",
        skills=[{"category": "Cloud", "items": ["AWS", "Terraform"]}],
        experience=[
            TailoredExperience(
                role="Senior Architect",
                company="PLACEHOLDER – Company A",
                period="2021–2024",
                achievements=["Led cloud migration saving £200K annually via platform consolidation."],
            )
        ],
        certifications=["PLACEHOLDER_CERT"],
    )


_MASTER_CV = {
    "experience": [
        {
            "achievements": [
                {"text": "Led cloud migration saving £200K annually via platform consolidation."},
                {"text": "Delivered £500K cost reduction via cloud architecture at Northern Powergrid."},
            ]
        }
    ]
}


# ---------------------------------------------------------------------------
# blocking_issues field exists on TailoredCVResult
# ---------------------------------------------------------------------------

def test_tailored_cv_result_has_blocking_issues_field():
    """TailoredCVResult must expose a blocking_issues field (not just fabrication_warnings)."""
    result = _make_clean_result()
    assert hasattr(result, "blocking_issues"), (
        "TailoredCVResult must have blocking_issues field to surface critical issues to the Review gate."
    )


# ---------------------------------------------------------------------------
# Placeholder detection in tailored result
# ---------------------------------------------------------------------------

def test_placeholder_in_summary_yields_blocking_issue():
    """[Company Name] in generated summary must be a blocking issue."""
    from app.services.cv_tailor import CVTailor
    tailor = CVTailor.__new__(CVTailor)
    result = _make_placeholder_result()
    blocking, advisory = tailor._validate_no_fabrication(result, _MASTER_CV)
    assert any("[Company Name]" in b or "summary" in b.lower() for b in blocking), (
        f"Expected blocking issue for summary placeholder, got: {blocking}"
    )


def test_placeholder_in_experience_header_yields_blocking_issue():
    """PLACEHOLDER in experience company header must be a blocking issue."""
    from app.services.cv_tailor import CVTailor
    tailor = CVTailor.__new__(CVTailor)
    result = _make_placeholder_result()
    blocking, _ = tailor._validate_no_fabrication(result, _MASTER_CV)
    assert any("company" in b.lower() or "placeholder" in b.lower() for b in blocking), (
        f"Expected blocking for placeholder company, got: {blocking}"
    )


def test_placeholder_in_certifications_yields_blocking_issue():
    """PLACEHOLDER in certifications must be a blocking issue."""
    from app.services.cv_tailor import CVTailor
    tailor = CVTailor.__new__(CVTailor)
    result = _make_placeholder_result()
    blocking, _ = tailor._validate_no_fabrication(result, _MASTER_CV)
    assert len(blocking) > 0


def test_clean_result_has_no_blocking_issues():
    """A clean tailored result must have no blocking issues."""
    from app.services.cv_tailor import CVTailor
    tailor = CVTailor.__new__(CVTailor)
    blocking, _ = tailor._validate_no_fabrication(_make_clean_result(), _MASTER_CV)
    assert blocking == [], f"Clean result should have no blocking issues, got: {blocking}"


# ---------------------------------------------------------------------------
# Advisory: fuzzy achievement check (pre-existing)
# ---------------------------------------------------------------------------

def test_invented_achievement_yields_advisory_warning():
    """An achievement with no master-CV grounding must yield an advisory warning."""
    from app.services.cv_tailor import CVTailor
    tailor = CVTailor.__new__(CVTailor)
    result = TailoredCVResult(
        summary="Solid summary with real content.",
        skills=[],
        experience=[
            TailoredExperience(
                role="Architect",
                company="Real Corp",
                period="2020–2023",
                achievements=["Invented a time-travel device using blockchain and quantum synergy."],
            )
        ],
        certifications=[],
    )
    _, advisory = tailor._validate_no_fabrication(result, _MASTER_CV)
    assert len(advisory) > 0, "Invented achievement must yield an advisory warning"


# ---------------------------------------------------------------------------
# tailor() populates result.blocking_issues
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tailor_populates_blocking_issues_on_placeholder_result():
    """tailor() must set result.blocking_issues when the generated CV has placeholders."""
    from app.services.cv_tailor import CVTailor

    mock_client = MagicMock()
    mock_client.complete_json = AsyncMock(return_value={
        "summary": "Led delivery at [Company Name], achieving results.",
        "skills": [],
        "experience": [],
        "certifications": [],
        "ats_keywords_embedded": [],
        "tailoring_notes": "",
    })

    _CLEAN_MASTER = {
        "personal": {"full_name": "Jane", "email": "jane@real.com", "phone": "+44 7700 900000"},
        "summary_variants": {"default": "Real summary"},
        "experience": [],
        "skills": {},
        "certifications": [],
    }

    tailor = CVTailor(mock_client)
    with patch.object(tailor, "_load_master_cv", return_value=_CLEAN_MASTER):
        result = await tailor.tailor(JDAnalysisResult(role_title="Test Role"))

    assert len(result.blocking_issues) > 0, (
        "tailor() must populate blocking_issues when generated summary contains [Company Name]"
    )
