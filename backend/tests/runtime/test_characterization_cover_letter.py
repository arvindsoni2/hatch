"""Characterize the current cover-letter parser result contract."""

from app.services.cl_generator import _parse_cover_letter


def test_legacy_cover_letter_result_shape_and_derived_word_count(runtime_fixture) -> None:
    raw = runtime_fixture("cover_letter_cases.json")
    result = _parse_cover_letter(raw)
    payload = result.model_dump(mode="json")

    assert set(payload) == {
        "subject_line",
        "greeting",
        "body_paragraphs",
        "sign_off",
        "word_count",
        "key_keywords_used",
        "grounding_issues",
        "validation_status",
        "validation_issues",
        "attempt_count",
        "repair_count",
        "first_pass_word_count",
    }
    assert payload["word_count"] == 26
    assert payload["word_count"] != raw["word_count"]
    assert payload["validation_status"] == "passed"
