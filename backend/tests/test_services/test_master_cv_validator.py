"""Tests for master-CV pre-flight validation and markup normalisation.

validate_master_cv()  — returns a list of field-level error strings for
                         placeholder tokens that would break the output.
normalise_master_cv() — returns a new dict with LaTeX/markup artefacts
                         cleaned up in-place.
CVTailor.tailor()     — raises MasterCVError when validation finds blockers.
"""
from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CLEAN_CV: dict = {
    "personal": {
        "full_name": "Jane Smith",
        "email": "jane@example.com",
        "phone": "+44 7700 900000",
        "linkedin": "https://linkedin.com/in/janesmith",
    },
    "summary_variants": {"default": "An experienced architect."},
    "experience": [
        {
            "role": "Senior Architect",
            "company": "Acme Corp",
            "achievements": [{"text": "Reduced costs by 30%", "tags": ["cost"]}],
        }
    ],
    "skills": {},
    "certifications": [],
}

_PLACEHOLDER_CV: dict = {
    "personal": {
        "full_name": "Arvind Soni",
        "email": "your.email@domain.com",
        "phone": "+44 XXXX XXXXXX",
        "linkedin": "https://linkedin.com/in/your-profile",
    },
    "summary_variants": {"default": "PLACEHOLDER – Company A led delivery."},
    "experience": [
        {
            "role": "Delivery Lead",
            "company": "PLACEHOLDER – Company A",
            "achievements": [{"text": "Saved £500K via mobile platform", "tags": ["cost"]}],
        }
    ],
    "skills": {},
    "certifications": [],
}

_LATEX_CV: dict = {
    "personal": {
        "full_name": "Bob Jones",
        "email": "bob@example.com",
        "phone": "+44 7700 900001",
    },
    "summary_variants": {"default": r"Delivered \$2M savings and \textsterling 500K efficiency gains. R\&D expert."},
    "experience": [
        {
            "role": "Architect",
            "company": "Energy Co",
            "achievements": [{"text": r"Cost reduction of \textsterling 200K via API consolidation", "tags": []}],
        }
    ],
    "skills": {},
    "certifications": [],
}


# ---------------------------------------------------------------------------
# validate_master_cv — placeholder detection
# ---------------------------------------------------------------------------

def test_validate_clean_cv_returns_no_errors():
    from app.services.master_cv_validator import validate_master_cv
    errors = validate_master_cv(_CLEAN_CV)
    assert errors == []


def test_validate_detects_placeholder_email():
    from app.services.master_cv_validator import validate_master_cv
    errors = validate_master_cv(_PLACEHOLDER_CV)
    assert any("email" in e.lower() for e in errors), f"Expected email error in: {errors}"


def test_validate_detects_xxxx_phone():
    from app.services.master_cv_validator import validate_master_cv
    errors = validate_master_cv(_PLACEHOLDER_CV)
    assert any("phone" in e.lower() for e in errors), f"Expected phone error in: {errors}"


def test_validate_detects_placeholder_in_summary():
    from app.services.master_cv_validator import validate_master_cv
    errors = validate_master_cv(_PLACEHOLDER_CV)
    assert any("placeholder" in e.lower() for e in errors), f"Expected placeholder error in: {errors}"


def test_validate_detects_placeholder_in_experience_header():
    from app.services.master_cv_validator import validate_master_cv
    errors = validate_master_cv(_PLACEHOLDER_CV)
    # company name with PLACEHOLDER token should be caught
    assert len(errors) > 0


def test_validate_clean_cv_passes():
    from app.services.master_cv_validator import validate_master_cv
    errors = validate_master_cv(_CLEAN_CV)
    assert errors == [], f"Clean CV should have no errors, got: {errors}"


# ---------------------------------------------------------------------------
# normalise_master_cv — markup cleanup
# ---------------------------------------------------------------------------

def test_normalise_strips_textsterling():
    from app.services.master_cv_validator import normalise_master_cv
    result = normalise_master_cv(_LATEX_CV)
    summary = list(result["summary_variants"].values())[0]
    assert r"\textsterling" not in summary
    assert "£" in summary


def test_normalise_converts_latex_amp():
    from app.services.master_cv_validator import normalise_master_cv
    result = normalise_master_cv(_LATEX_CV)
    summary = list(result["summary_variants"].values())[0]
    assert r"\&" not in summary
    assert "&" in summary


def test_normalise_strips_math_dollar():
    from app.services.master_cv_validator import normalise_master_cv
    result = normalise_master_cv(_LATEX_CV)
    summary = list(result["summary_variants"].values())[0]
    assert r"\$" not in summary


def test_normalise_does_not_mutate_input():
    from app.services.master_cv_validator import normalise_master_cv
    original_summary = list(_LATEX_CV["summary_variants"].values())[0]
    normalise_master_cv(_LATEX_CV)
    assert list(_LATEX_CV["summary_variants"].values())[0] == original_summary


def test_normalise_experience_achievements():
    from app.services.master_cv_validator import normalise_master_cv
    result = normalise_master_cv(_LATEX_CV)
    ach = result["experience"][0]["achievements"][0]["text"]
    assert r"\textsterling" not in ach
    assert "£" in ach


# ---------------------------------------------------------------------------
# CVTailor.tailor() raises on unfilled master CV
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tailor_raises_on_placeholder_master_cv():
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.services.cv_tailor import CVTailor
    from app.services.master_cv_validator import MasterCVError
    from app.schemas.tailor import JDAnalysisResult

    mock_client = MagicMock()
    mock_client.complete_json = AsyncMock()  # should never be called

    tailor = CVTailor(mock_client)
    with patch.object(tailor, "_load_master_cv", return_value=_PLACEHOLDER_CV):
        with pytest.raises(MasterCVError) as exc_info:
            await tailor.tailor(JDAnalysisResult(role_title="Test Role"))

    assert "your.email" in str(exc_info.value).lower() or "placeholder" in str(exc_info.value).lower()
    mock_client.complete_json.assert_not_called()


@pytest.mark.asyncio
async def test_tailor_proceeds_with_clean_master_cv():
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.services.cv_tailor import CVTailor
    from app.schemas.tailor import JDAnalysisResult

    mock_client = MagicMock()
    mock_client.complete_json = AsyncMock(return_value={
        "summary": "Clean summary", "skills": [], "experience": [],
        "certifications": [], "ats_keywords_embedded": [], "tailoring_notes": "",
    })

    tailor = CVTailor(mock_client)
    with patch.object(tailor, "_load_master_cv", return_value=_CLEAN_CV):
        result = await tailor.tailor(JDAnalysisResult(role_title="Test Role"))

    assert result.summary == "Clean summary"
    mock_client.complete_json.assert_called_once()
