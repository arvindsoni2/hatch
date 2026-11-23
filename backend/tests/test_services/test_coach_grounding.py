"""Production grounding checks shared with the Phase 2 bench."""
from __future__ import annotations

from app.services.coach_readiness import grounding


def _case() -> dict:
    return {
        "dimension": "specificity",
        "rubric_description": "Name the result in plain words.",
        "excerpts": [
            {
                "excerpt_id": "e1",
                "text": "Name the result in plain words.",
                "session_date": "2026-11-01",
                "difficulty": "realistic",
            }
        ],
    }


def test_grounding_rejects_unknown_ids_and_new_numbers() -> None:
    output = {"tips": ["We saved 42% at Acme."]}

    violations = grounding.grounding_violations("explain", output, _case())

    assert any(item.startswith("number_not_in_source") for item in violations)
    assert any(item.startswith("name_not_in_source") for item in violations)


def test_explain_word_limits() -> None:
    too_many = {"tips": ["a", "b", "c", "d"]}
    too_long = {"tips": ["word " * 41]}
    too_much = {"tips": ["word " * 40, "word " * 40, "word " * 40, "word " * 1]}

    assert grounding.grounding_violations("explain", too_many, _case())
    assert grounding.grounding_violations("explain", too_long, _case())
    assert grounding.grounding_violations("explain", too_much, _case())
