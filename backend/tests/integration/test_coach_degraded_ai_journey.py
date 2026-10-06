"""V6 Scenario G: transcription survives evaluator unavailability."""

import asyncio
import base64
import hashlib
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from coach_app_process import CoachAppProcess


AUDIO_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "frontend/e2e/fixtures/coach-synthetic-tone.webm.b64"
)
ANSWER = "I led the migration and reduced deployment time by three hours."


async def _wait_for_setup(client: httpx.AsyncClient, base_url: str, job_id: str) -> None:
    async with asyncio.timeout(20):
        while True:
            response = await client.get(f"{base_url}/api/async-jobs/{job_id}")
            assert response.status_code == 200
            job = response.json()
            if job["status"] == "done":
                return
            assert job["status"] != "failed", job
            await asyncio.sleep(0.1)


async def _live(client: httpx.AsyncClient, base_url: str, session_id: str) -> dict:
    response = await client.get(f"{base_url}/api/coach/sessions/{session_id}/live")
    assert response.status_code == 200, response.text
    return response.json()


async def _command(
    client: httpx.AsyncClient,
    base_url: str,
    session_id: str,
    command_type: str,
    payload: dict,
) -> dict:
    live = await _live(client, base_url, session_id)
    response = await client.post(
        f"{base_url}/api/coach/sessions/{session_id}/commands",
        json={
            "command_id": str(uuid4()),
            "command_type": command_type,
            "expected_state_version": live["state_version"],
            "payload": payload,
            "contract_version": "coach_conversation_command_v1",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_audio_transcript_survives_unavailable_evaluator_and_can_continue(tmp_path):
    """A failed evaluator must not erase ASR text or invent a candidate level."""
    async with CoachAppProcess(
        tmp_path / "degraded.db",
        tmp_path / "media",
        app_module="coach_degraded_test_server:app",
    ) as app_process:
        base_url = app_process.base_url
        async with httpx.AsyncClient(timeout=5) as client:
            created = await client.post(
                f"{base_url}/api/coach/sessions",
                json={
                    "company_name": "Synthetic Browser Co",
                    "role_title": "Engineer",
                    "jd_text": "Build reliable software.",
                    "experience_version": "conversational_v1",
                    "conversational_config": {
                        "interview_type": "mixed",
                        "difficulty": "realistic",
                        "duration_minutes": 30,
                        "planned_question_count": 6,
                        "role_family": "software_engineering",
                        "role_level": "senior",
                        "industry": "technology",
                        "locale": "en-GB",
                        "focus_areas": ["delivery_execution"],
                        "allowed_answer_modes": ["text", "audio"],
                        "evidence_selection": {
                            "application_cv": "none",
                            "master_cv": "exclude",
                            "question_bank": "exclude",
                            "company_research": "exclude",
                            "draft_evidence_consent": False,
                        },
                    },
                },
            )
            assert created.status_code == 202, created.text
            session_id = created.json()["session_id"]
            await _wait_for_setup(client, base_url, created.json()["job_id"])
            await _command(client, base_url, session_id, "start", {})
            begun = await _command(
                client,
                base_url,
                session_id,
                "begin_answer",
                {"recording_type": "audio", "client_attempt_id": str(uuid4())},
            )
            attempt_id = begun["active_attempt_id"]
            audio = base64.b64decode(AUDIO_FIXTURE.read_text(encoding="ascii"))
            upload_id = str(uuid4())
            uploaded = await client.post(
                f"{base_url}/api/coach/sessions/{session_id}/attempts/{attempt_id}/audio",
                data={
                    "upload_id": upload_id,
                    "content_sha256": hashlib.sha256(audio).hexdigest(),
                },
                files={"audio": ("synthetic-tone.webm", audio, "audio/webm")},
            )
            assert uploaded.status_code == 200, uploaded.text
            await _command(
                client,
                base_url,
                session_id,
                "finish_answer",
                {"attempt_id": attempt_id, "upload_id": upload_id},
            )
            async with asyncio.timeout(30):
                while True:
                    live = await _live(client, base_url, session_id)
                    if live["conversation_state"] == "awaiting_next_action":
                        break
                    await asyncio.sleep(0.1)
            assert live["active_attempt"]["transcript_version"]["transcript"] == ANSWER
            assert live["answer_review"]["evaluation_state"] == "unavailable"
            assert live["answer_review"]["answer_level"] == "not_assessed"
            assert "accept_attempt" in live["allowed_commands"]
            await _command(
                client,
                base_url,
                session_id,
                "accept_attempt",
                {"attempt_id": attempt_id},
            )
            continued = await _live(client, base_url, session_id)
            assert continued["progress"]["planned_questions_completed"] == 1
    log_text = (tmp_path / "coach-app-process.log").read_text(encoding="utf-8")
    assert "openai._base_client" not in log_text
    assert "faster_whisper" not in log_text
