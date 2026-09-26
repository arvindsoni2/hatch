"""Characterize the current tailored-CV parser result contract."""

from app.services.cv_tailor import _parse_tailored_cv


def test_legacy_tailored_cv_result_shape(runtime_fixture) -> None:
    result = _parse_tailored_cv(runtime_fixture("tailoring_cases.json"))
    payload = result.model_dump(mode="json")

    assert set(payload) == {
        "summary",
        "skills",
        "experience",
        "education",
        "certifications",
        "ats_keywords_embedded",
        "tailoring_notes",
        "structural_warnings",
        "validation_status",
        "blocking_issues",
        "fabrication_warnings",
    }
    assert payload["experience"][0]["role"] == "Platform Architect"
    assert payload["education"][0]["qualification"] == "BSc Computer Science"
    assert payload["validation_status"] == "passed"
