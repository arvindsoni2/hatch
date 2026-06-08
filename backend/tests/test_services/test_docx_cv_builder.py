"""T10: docx_cv_builder skill-label field mismatch fix."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from app.services.docx_cv_builder import _build_cv_spec
from app.schemas.tailor import TailoredCVResult, JDAnalysisResult


def _make_tailored_cv(**kwargs) -> TailoredCVResult:
    defaults = {
        "summary": "Test summary.",
        "skills": [],
        "experience": [],
        "certifications": [],
        "ats_keywords_embedded": [],
        "tailoring_notes": "none",
        "fabrication_warnings": [],
        "blocking_issues": [],
    }
    defaults.update(kwargs)
    return TailoredCVResult(**defaults)


def _make_jd() -> JDAnalysisResult:
    return JDAnalysisResult(role_title="Senior Engineer")


def test_build_spec_uses_category_field():
    cv = _make_tailored_cv(skills=[{"category": "Cloud & Infrastructure", "items": ["AWS", "Azure"]}])
    spec = _build_cv_spec(cv, _make_jd(), {"name": "Test"})
    assert spec["skills"][0]["display_name"] == "Cloud & Infrastructure"


def test_build_spec_falls_back_to_display_name():
    cv = _make_tailored_cv(skills=[{"display_name": "Data & AI", "items": ["Python"]}])
    spec = _build_cv_spec(cv, _make_jd(), {"name": "Test"})
    assert spec["skills"][0]["display_name"] == "Data & AI"


def test_build_spec_falls_back_to_name():
    cv = _make_tailored_cv(skills=[{"name": "Delivery", "items": ["Agile"]}])
    spec = _build_cv_spec(cv, _make_jd(), {"name": "Test"})
    assert spec["skills"][0]["display_name"] == "Delivery"


def test_build_spec_category_wins_over_display_name():
    cv = _make_tailored_cv(skills=[{"category": "Security & Compliance", "display_name": "OLD", "items": ["ISO 27001"]}])
    spec = _build_cv_spec(cv, _make_jd(), {"name": "Test"})
    assert spec["skills"][0]["display_name"] == "Security & Compliance"


def test_build_spec_empty_label_returns_empty_string():
    cv = _make_tailored_cv(skills=[{"items": ["Python"]}])
    spec = _build_cv_spec(cv, _make_jd(), {"name": "Test"})
    assert spec["skills"][0]["display_name"] == ""


def test_build_spec_preserves_items():
    cv = _make_tailored_cv(skills=[{"category": "Data & AI", "items": ["SQL", "Spark", "dbt"]}])
    spec = _build_cv_spec(cv, _make_jd(), {"name": "Test"})
    assert spec["skills"][0]["items"] == ["SQL", "Spark", "dbt"]


def test_build_spec_multiple_skill_groups():
    cv = _make_tailored_cv(skills=[
        {"category": "Cloud & Infrastructure", "items": ["AWS"]},
        {"category": "Data & AI", "items": ["Python"]},
    ])
    spec = _build_cv_spec(cv, _make_jd(), {"name": "Test"})
    labels = [s["display_name"] for s in spec["skills"]]
    assert labels == ["Cloud & Infrastructure", "Data & AI"]
