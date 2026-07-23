from __future__ import annotations

import pytest

from app.observability.attributes import (
    ALLOWED_ATTRIBUTE_KEYS,
    FAILED_GATE_CODES,
    MODEL_ID,
    PROMPT_ID,
    sanitize_attributes,
)
from app.observability.runtime import SafeSpan


def test_attributes_allow_only_hatch_owned_low_cardinality_contract() -> None:
    attributes = sanitize_attributes(
        {
            MODEL_ID: "qwen35-4b",
            PROMPT_ID: "cover_letter_generation",
            FAILED_GATE_CODES: ["numeric_fidelity", "body_length"],
            "prompt.text": "private prompt",
            "candidate.email": "person@example.test",
            "filesystem.path": "/home/person/private/cv.docx",
        }
    )

    assert attributes == {
        MODEL_ID: "qwen35-4b",
        PROMPT_ID: "cover_letter_generation",
        FAILED_GATE_CODES: ("numeric_fidelity", "body_length"),
    }


def test_attribute_values_are_bounded_and_secret_shaped_values_are_dropped() -> None:
    attributes = sanitize_attributes(
        {
            MODEL_ID: "x" * 300,
            PROMPT_ID: "Bearer private-token",
            "hatch.ai.document.id": "/home/user/private/cv.docx",
        }
    )

    assert attributes == {MODEL_ID: "x" * 128}


def test_exception_payload_and_arbitrary_event_name_are_not_forwarded() -> None:
    calls: list[tuple[str, object]] = []

    class RawSpan:
        def record_exception(self, exception) -> None:
            calls.append(("exception", exception))

        def add_event(self, name, attributes) -> None:
            calls.append(("event", (name, attributes)))

    span = SafeSpan(RawSpan())
    span.record_exception(
        RuntimeError("Bearer private-token in /home/user/private-cv.txt")
    )
    span.add_event("Bearer private-token", {"prompt.text": "private CV"})

    assert calls == [("event", ("telemetry_event", {}))]


@pytest.mark.parametrize(
    ("key", "sentinel"),
    [
        ("candidate.cv", "Private CV sentinel"),
        ("job.description", "Private JD sentinel"),
        ("coach.question.text", "Private question sentinel"),
        ("coach.model_answer.text", "Private model answer sentinel"),
        ("coach.answer.transcript", "Private transcript sentinel"),
        ("coach.audio.path", "/home/private/audio-sentinel.wav"),
        ("coach.performance.score", "9.75"),
    ],
)
def test_prohibited_coach_content_has_no_telemetry_attribute(
    key: str,
    sentinel: str,
) -> None:
    assert sanitize_attributes({key: sentinel}) == {}
    assert key not in ALLOWED_ATTRIBUTE_KEYS


def test_authoritative_ai_attribute_names_have_no_conflicting_aliases() -> None:
    assert "hatch.ai.workflow" not in ALLOWED_ATTRIBUTE_KEYS
    assert "hatch.ai.provider" not in ALLOWED_ATTRIBUTE_KEYS
    assert "hatch.ai.model_id" not in ALLOWED_ATTRIBUTE_KEYS
