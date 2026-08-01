"""HTTP trust-boundary tests for conversational audio capture."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.config import settings
from app.models.coach_session import (
    InterviewAttemptUpload,
    InterviewSession,
    SessionRecording,
)


@pytest.fixture
def isolated_media_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "isolated-coach-media"
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", root)
    monkeypatch.setattr(settings, "HATCH_COACH_MAX_AUDIO_BYTES", 64)
    return root


@pytest_asyncio.fixture
async def seeded_listening_audio_attempt(db_session, isolated_media_root):
    session = InterviewSession(
        id="capture-session-1",
        company_name="Example Co",
        role_title="Architect",
        config={},
        status="active",
        experience_version="conversational_v1",
        conversation_state="listening",
        active_recording_id="capture-attempt-1",
        retention_policy_json={"audio": "delete_after_processing"},
    )
    attempt = SessionRecording(
        id="capture-attempt-1",
        session_id=session.id,
        recording_type="audio",
        attempt_state="draft",
        audio_retention_policy="delete_after_processing",
        audio_retention_state="pending",
        processing_retry_limit=2,
        client_attempt_id="capture-client-1",
    )
    db_session.add_all((session, attempt))
    await db_session.commit()
    return session, attempt


def _url(session_id: str = "capture-session-1", attempt_id: str = "capture-attempt-1") -> str:
    return f"/api/coach/sessions/{session_id}/attempts/{attempt_id}/audio"


async def _completed_upload_count(db_session) -> int:
    return int(
        await db_session.scalar(
            select(func.count(InterviewAttemptUpload.id)).where(
                InterviewAttemptUpload.result_state == "completed"
            )
        )
        or 0
    )


def _temporary_uploads(root: Path) -> list[Path]:
    return list(root.rglob("coach-upload-*")) if root.exists() else []


@pytest.mark.asyncio
async def test_audio_upload_is_hash_verified_and_idempotent(
    client, db_session, seeded_listening_audio_attempt, isolated_media_root
) -> None:
    """Removing replay lookup would create a second receipt or fail the retry."""
    body = b"synthetic-webm"
    digest = hashlib.sha256(body).hexdigest()
    first = await client.post(
        _url(),
        data={"upload_id": "upload-1", "content_sha256": digest},
        files={"audio": ("../../x.webm", body, "audio/webm; codecs=opus")},
    )
    replay = await client.post(
        _url(),
        data={"upload_id": "upload-1", "content_sha256": digest},
        files={"audio": ("different.webm", body, "audio/webm")},
    )

    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert first.json() == {
        "attempt_id": "capture-attempt-1",
        "upload_id": "upload-1",
        "result": "completed",
        "content_sha256": digest,
        "byte_size": len(body),
        "mime_type": "audio/webm",
        "audio_retention_state": "temporary",
        "contract_version": "coach_attempt_audio_upload_v1",
    }
    assert await _completed_upload_count(db_session) == 1
    assert not _temporary_uploads(isolated_media_root)
    for untrusted in ("../../x.webm", "different.webm", body.decode()):
        assert untrusted not in first.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    ["wrong_session", "wrong_attempt", "bad_hash", "too_large", "bad_mime", "symlink_escape"],
)
async def test_audio_upload_rejects_untrusted_case_without_persistence(
    case,
    client,
    db_session,
    seeded_listening_audio_attempt,
    isolated_media_root,
    monkeypatch,
) -> None:
    """Removing any upload trust fence would leave a completed receipt or temp."""
    body = b"synthetic-webm"
    digest = hashlib.sha256(body).hexdigest()
    url = _url()
    mime_type = "audio/webm"
    if case == "wrong_session":
        url = _url(session_id="another-session")
    elif case == "wrong_attempt":
        url = _url(attempt_id="another-attempt")
    elif case == "bad_hash":
        digest = "0" * 64
    elif case == "too_large":
        monkeypatch.setattr(settings, "HATCH_COACH_MAX_AUDIO_BYTES", 3)
    elif case == "bad_mime":
        mime_type = "application/octet-stream"
    elif case == "symlink_escape":
        isolated_media_root.mkdir(parents=True)
        outside = isolated_media_root.parent / "outside"
        outside.mkdir()
        (isolated_media_root / "capture-session-1").symlink_to(
            outside, target_is_directory=True
        )

    response = await client.post(
        url,
        data={"upload_id": "upload-1", "content_sha256": digest},
        files={"audio": ("../../private.webm", body, mime_type)},
    )

    assert response.status_code in {400, 404, 409, 413, 422}
    assert response.json()["error"]["code"] in {
        "coach_attempt_upload_conflict",
        "coach_attempt_upload_hash_mismatch",
        "coach_attempt_upload_missing",
    }
    assert response.json()["error"]["details"] == {}
    assert await _completed_upload_count(db_session) == 0
    assert not _temporary_uploads(isolated_media_root)
    assert "../../private.webm" not in response.text
    assert str(isolated_media_root) not in response.text
    assert body.decode() not in response.text


@pytest.mark.asyncio
async def test_audio_upload_uses_only_configured_media_root(
    client, db_session, seeded_listening_audio_attempt, isolated_media_root
) -> None:
    """Using a CWD-relative media path would put the receipt outside the setting."""
    body = b"configured-root-webm"
    digest = hashlib.sha256(body).hexdigest()

    response = await client.post(
        _url(),
        data={"upload_id": "upload-root", "content_sha256": digest},
        files={"audio": ("answer.webm", body, "audio/webm")},
    )

    assert response.status_code == 200
    upload = await db_session.scalar(select(InterviewAttemptUpload))
    assert upload is not None
    root = isolated_media_root.resolve()
    stored = Path(upload.storage_uri).resolve()
    assert stored.is_relative_to(root)
    assert stored.read_bytes() == body
    assert all(
        path.resolve().is_relative_to(root)
        for path in isolated_media_root.rglob("*")
    )
