from __future__ import annotations

import pytest

from app.services.writing_contracts import (
    EVIDENCE_SCHEMA_VERSION,
    build_evidence_ledger,
    extract_numeric_tokens,
    normalize_evidence_text,
    stable_evidence_id,
    validate_numeric_fidelity,
)


def test_evidence_ids_are_stable_and_duplicates_keep_first_source() -> None:
    master = {
        "summary_variants": {
            "a": "Delivered across 120+ locations",
            "b": " Delivered  across  120+ locations ",
        },
    }

    ledger = build_evidence_ledger(master)

    assert EVIDENCE_SCHEMA_VERSION == "1.0.0"
    assert len(ledger) == 1
    assert ledger[0].source_path == "summary_variants.a"
    assert ledger[0].id == "0516177ba0bd38d2800c3398"
    assert ledger[0].id == stable_evidence_id(
        "summary_variants.a",
        "Delivered across 120+ locations",
    )


def test_evidence_normalization_preserves_case_punctuation_and_numeric_formatting() -> None:
    decomposed = "Cafe\u0301\r\n  delivery\tacross  £2.5m."

    assert normalize_evidence_text(decomposed) == "Café delivery across £2.5m."


def test_evidence_ledger_preserves_source_order_and_types() -> None:
    master = {
        "summary_variants": {"delivery": "Delivery leader"},
        "experience": [
            {
                "role": "Delivery Manager",
                "company": "Example Ltd",
                "period": "2018–2022",
                "achievements": [
                    {"text": "Improved throughput by 15%"},
                    "Managed 120+ locations",
                ],
            }
        ],
        "skills": {
            "delivery": {
                "category": "Delivery",
                "items": ["Scrum"],
            }
        },
        "education": [{"qualification": "BSc Computer Science"}],
        "certifications": ["PSM I"],
    }

    ledger = build_evidence_ledger(master)

    assert [(item.source_path, item.evidence_type) for item in ledger] == [
        ("summary_variants.delivery", "profile_summary"),
        ("experience.0.achievements.0", "achievement"),
        ("experience.0.achievements.1", "achievement"),
        ("skills.delivery.items.0", "skill"),
        ("education.0.qualification", "education"),
        ("certifications.0", "certification"),
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Managed 120+ locations", ("120+ locations",)),
        ("Owned a £2.5m budget", ("£2.5m budget",)),
        ("Improved throughput by 15%", ("15%",)),
        ("Served from 2018–2022", ("2018–2022",)),
        ("Supported +25 sites", ("+25 sites",)),
        ("Saved £2 million", ("£2 million",)),
    ],
)
def test_extract_numeric_tokens_preserves_immutable_expression(
    text: str,
    expected: tuple[str, ...],
) -> None:
    assert tuple(item.raw for item in extract_numeric_tokens(text)) == expected


def test_numeric_validation_blocks_mutated_and_unsupported_tokens() -> None:
    ledger = build_evidence_ledger(
        {
            "experience": [
                {
                    "achievements": [
                        {"text": "Managed delivery across 120+ locations"},
                    ]
                }
            ]
        }
    )

    result = validate_numeric_fidelity(
        ["Managed delivery across 120 locations and improved throughput by 97%."],
        ledger,
    )

    assert not result.passed
    assert [issue.code for issue in result.issues] == [
        "unsupported_numeric_token",
        "unsupported_numeric_token",
    ]
    assert [issue.observed for issue in result.issues] == ["120 locations", "97%"]


def test_numeric_dates_and_metadata_outside_candidate_prose_are_not_false_positives() -> None:
    ledger = build_evidence_ledger(
        {
            "experience": [
                {
                    "role": "Delivery Manager",
                    "period": "2018–2022",
                    "achievements": [{"text": "Delivered the migration safely"}],
                }
            ]
        }
    )

    result = validate_numeric_fidelity(
        ["Delivered the migration safely."],
        ledger,
    )

    assert result.passed
    assert result.issues == ()
