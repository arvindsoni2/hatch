"""Tests that coach endpoints return 202 + job_id."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Existing session/answer async tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_session_returns_202(client):
    """POST /api/coach/sessions returns 202 with job_id."""
    response = await client.post(
        "/api/coach/sessions",
        json={
            "company_name": "Acme Corp",
            "role_title": "Senior Developer",
            "config": {
                "question_count": 5,
                "categories": ["Technical"],
                "recording_mode": "text",
                "difficulty": "medium",
            },
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "coach_session"


@pytest.mark.asyncio
async def test_submit_answer_returns_202(client):
    """POST /api/coach/sessions/{id}/submit-answer returns 202 with job_id."""
    response = await client.post(
        "/api/coach/sessions/fake-session-id/submit-answer",
        params={"question_id": "fake-q-id"},
        json={"transcript": "I led a team...", "duration_ms": 45000},
    )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "submit_answer"


@pytest.mark.asyncio
async def test_end_session_returns_202(client):
    """POST /api/coach/sessions/{id}/end returns 202 with job_id."""
    response = await client.post("/api/coach/sessions/fake-session-id/end")
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "end_session"


# ---------------------------------------------------------------------------
# Phase A Task 4 — submit-audio endpoint
# ---------------------------------------------------------------------------

# Minimal valid WAV: RIFF header + WAVE marker (no audio data; just needs to be readable)
_WAV_HEADER = (
    b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00"
    b"\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00"
    b"data\x00\x00\x00\x00"
)


@pytest.mark.asyncio
async def test_submit_audio_returns_202(client, tmp_path, monkeypatch):
    """POST /api/coach/sessions/{id}/submit-audio returns 202 with job_id and type."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    response = await client.post(
        "/api/coach/sessions/s-audio-test/submit-audio",
        files={"audio": ("answer.wav", _WAV_HEADER, "audio/wav")},
        data={"question_id": "q-audio-001"},
    )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "submit_audio"


@pytest.mark.asyncio
async def test_submit_audio_rejects_non_audio_content_type(client, tmp_path, monkeypatch):
    """POST /api/coach/sessions/{id}/submit-audio returns 400 for non-audio content-type."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    response = await client.post(
        "/api/coach/sessions/s-audio-test/submit-audio",
        files={"audio": ("answer.txt", b"plain text content", "text/plain")},
        data={"question_id": "q-audio-001"},
    )
    assert response.status_code == 400
    assert "Audio files only" in response.json()["detail"]


@pytest.mark.asyncio
async def test_submit_audio_saves_file_to_recordings_dir(client, tmp_path, monkeypatch):
    """POST /api/coach/sessions/{id}/submit-audio saves the audio blob to recordings/{session}/{question}.ext."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    response = await client.post(
        "/api/coach/sessions/s123/submit-audio",
        files={"audio": ("answer.wav", _WAV_HEADER, "audio/wav")},
        data={"question_id": "q456"},
    )
    assert response.status_code == 202
    saved = tmp_path / "recordings" / "s123" / "q456.wav"
    assert saved.exists(), f"Expected saved audio at {saved}"
    assert saved.read_bytes() == _WAV_HEADER
