"""Behavioural contracts for bounded conversational-capture settings."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import settings
from app.schemas.coach_conversation import AttemptAudioUploadRead


Settings = type(settings)


def test_pr2_defaults_and_bounds() -> None:
    """An unbounded answer limit would permit a capture resource exhaustion."""
    settings = Settings()

    assert settings.HATCH_COACH_TIMEOUT_CONVERSATIONAL_JOB_SECONDS == 900
    assert settings.HATCH_COACH_TIMEOUT_AUDIO_CLEANUP_JOB_SECONDS == 180
    assert settings.HATCH_COACH_AUDIO_FAILURE_RETENTION_HOURS == 24
    assert settings.HATCH_COACH_MEDIA_ROOT == Path("./data/coach-media")

    with pytest.raises(ValidationError):
        Settings(HATCH_COACH_MAX_ANSWER_DURATION_SECONDS=0)


def test_upload_read_rejects_non_hex_hash() -> None:
    """A malformed hash would prevent consumers from fencing an audio upload."""
    with pytest.raises(ValidationError):
        AttemptAudioUploadRead(
            attempt_id="attempt-1",
            upload_id="upload-1",
            result="completed",
            content_sha256="not-a-hash",
            byte_size=3,
            mime_type="audio/webm",
            audio_retention_state="temporary",
            contract_version="coach_attempt_audio_upload_v1",
        )


def test_upload_read_accepts_complete_bounded_metadata() -> None:
    """A valid persisted upload response remains consumable by the capture client."""
    upload = AttemptAudioUploadRead(
        attempt_id="attempt-1",
        upload_id="upload-1",
        result="completed",
        content_sha256="a" * 64,
        byte_size=3,
        mime_type="audio/webm",
        audio_retention_state="temporary",
        contract_version="coach_attempt_audio_upload_v1",
    )

    assert upload.model_dump() == {
        "attempt_id": "attempt-1",
        "upload_id": "upload-1",
        "result": "completed",
        "content_sha256": "a" * 64,
        "byte_size": 3,
        "mime_type": "audio/webm",
        "audio_retention_state": "temporary",
        "contract_version": "coach_attempt_audio_upload_v1",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("content_sha256", "A" * 64),
        ("byte_size", 0),
        ("mime_type", ""),
        ("mime_type", "a" * 129),
    ],
)
def test_upload_read_rejects_invalid_hash_size_or_mime(
    field: str, value: str | int
) -> None:
    """Invalid upload metadata must not become a public persistence contract."""
    payload: dict[str, object] = {
        "attempt_id": "attempt-1",
        "upload_id": "upload-1",
        "result": "completed",
        "content_sha256": "a" * 64,
        "byte_size": 3,
        "mime_type": "audio/webm",
        "audio_retention_state": "temporary",
        "contract_version": "coach_attempt_audio_upload_v1",
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        AttemptAudioUploadRead(**payload)
