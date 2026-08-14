from __future__ import annotations

import pytest

from app.services.coach_text_spans import (
    ContractValidationError,
    normalize_contract_text,
    scan_prohibited_model_authorship,
    validate_code_point_span,
)


def test_span_validation_uses_nfc_lf_and_unicode_code_points() -> None:
    text = "A\r\nCafe\u0301 😀 नमस्ते"

    normalized = normalize_contract_text(text)

    assert normalized == "A\nCafé 😀 नमस्ते"
    start = normalized.index("😀")
    assert validate_code_point_span(text, start, start + 1, "😀").excerpt == "😀"


@pytest.mark.parametrize(
    ("start", "end", "excerpt"),
    [
        (0, 0, ""),
        (-1, 1, "A"),
        (0, 99, "A"),
        (True, 1, "A"),
        (0, False, "A"),
        (0, 1, "B"),
    ],
)
def test_span_validation_rejects_invalid_half_open_ranges(
    start: int, end: int, excerpt: str
) -> None:
    with pytest.raises(
        ContractValidationError,
        match="coach_evaluation_evidence_span_invalid",
    ):
        validate_code_point_span("A😀न", start, end, excerpt)


def test_span_validation_normalizes_quoted_combining_text() -> None:
    validated = validate_code_point_span("Cafe\u0301", 0, 4, "Café")

    assert validated.start == 0
    assert validated.end == 4
    assert validated.excerpt == "Café"


def test_prohibited_scan_targets_model_authorship_not_candidate_quote() -> None:
    assert scan_prohibited_model_authorship(
        {"rationale": "The candidate seems anxious and deceptive."}
    ) == ("anxious", "deceptive")
    assert (
        scan_prohibited_model_authorship(
            {
                "transcript_excerpt": "I felt anxious before the launch",
                "rationale": "This is a candidate quotation.",
            }
        )
        == ()
    )


def test_prohibited_scan_is_deterministic_and_traverses_model_authored_fields() -> None:
    value = {
        "coaching": [
            {"message": "They show culture fit and vocal confidence."},
            {"message": "This seems like a personality judgement."},
        ],
        "evidence": [{"excerpt": "My manager called me deceptive."}],
    }

    assert scan_prohibited_model_authorship(value) == (
        "culture fit",
        "vocal confidence",
        "personality",
    )
