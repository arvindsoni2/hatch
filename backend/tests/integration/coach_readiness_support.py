"""Shared synthetic harness for the P6 RED contract tests (Claude Code, plan §1.5).

Only the external model server is faked, at its HTTP boundary: llama.cpp's
OpenAI-compatible ``POST …/chat/completions``. Everything else is the real
readiness router, runtime and database. All data is synthetic.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import text

from app.config import settings
from app.database import get_db
from app.models.coach_session import InterviewSession, SessionRecording
from app.services.coach_conversational_contracts import CONTENT_DIMENSIONS
from app.services.coach_conversational_report import (
    AcceptedAnswer,
    ReportInputSnapshot,
    build_conversational_report,
)

READINESS = "/api/coach/readiness"
CHAT_COMPLETIONS = re.compile(r".*/chat/completions$")
TERMINAL = {"succeeded", "degraded", "fenced"}
TIPS = [
    "Name the decision you made yourself.",
    "Say what you did, not what the team did.",
    "Close with the result in plain words.",
]
SUPPORTING = ("p6-session-a", "p6-session-b")
# The synthetic report lists improvement priorities (Why? excerpts) for relevance.
EXPLAINED_DIMENSION = "relevance"
AUDIO_BYTES = b"synthetic p6 audio fixture"


def not_the_test_client(request: httpx.Request) -> bool:
    """pytest-httpx should_mock: never intercept the in-process ASGI client."""
    return request.url.host != "test"


def _report(session_id: str, canary: str | None) -> dict[str, Any]:
    report = build_conversational_report(
        ReportInputSnapshot(
            session_id=session_id,
            activity_version=1,
            retention_version=0,
            compatibility_key=f"key-{session_id}",
            counts={
                "planned_questions_total": 2,
                "planned_questions_answered": 2,
                "planned_questions_skipped": 0,
                "follow_ups_asked": 0,
                "follow_ups_answered": 0,
                "accepted_attempts": 2,
                "retry_attempts": 0,
                "unavailable_attempts": 0,
                "hints_used": 0,
            },
            accepted_root_bundles=tuple(
                (
                    AcceptedAnswer(
                        f"answer-{session_id}-{root}",
                        {dimension: "needs_work" for dimension in CONTENT_DIMENSIONS},
                    ),
                    (),
                )
                for root in (1, 2)
            ),
        )
    ).persisted_json()
    if canary is not None:
        # Put the canary in the stored report excerpts that Why? and Explain use.
        priorities = report["improvement_priorities"]
        assert any(item["dimension"] == EXPLAINED_DIMENSION for item in priorities)
        for item in priorities:
            item["next_action"] = f"{item['next_action']} ({canary})"
    return report


def _session(session_id: str, completed_at: datetime, canary: str | None) -> InterviewSession:
    return InterviewSession(
        id=session_id,
        company_name="Synthetic Ltd",
        role_title="Delivery Lead",
        config={},
        status="completed",
        conversation_state="completed",
        experience_version="conversational_v1",
        completed_at=completed_at,
        activity_version=1,
        state_version=1,
        report_state="completed",
        report_json=_report(session_id, canary),
        compatibility_key=f"key-{session_id}",
        session_plan_json={
            "role": {"role_family": "Delivery Lead", "role_level": "senior"},
            "interview": {"type": "behavioural", "difficulty": "realistic"},
        },
    )


async def seed_pattern_sessions(factory, *, canary: str | None = None) -> None:
    """Two recent sessions in one group, every dimension weak, one audio attempt each."""
    now = datetime.utcnow()
    media_root = Path(settings.HATCH_COACH_MEDIA_ROOT)
    async with factory() as db:
        for index, session_id in enumerate(SUPPORTING):
            db.add(_session(session_id, now - timedelta(days=2 - index), canary))
        await db.flush()
        for session_id in SUPPORTING:
            media = media_root / session_id / "answer.webm"
            media.parent.mkdir(parents=True, exist_ok=True)
            media.write_bytes(AUDIO_BYTES)
            db.add(
                SessionRecording(
                    id=f"{session_id}-attempt",
                    session_id=session_id,
                    recording_type="audio",
                    attempt_state="completed",
                    transcript=(
                        f"Synthetic transcript {canary}" if canary else "Synthetic transcript"
                    ),
                    audio_uri=str(media),
                    audio_content_hash=hashlib.sha256(AUDIO_BYTES).hexdigest(),
                    audio_retention_state="retained",
                )
            )
        await db.commit()


def configure_local_ai(tmp_path: Path, monkeypatch) -> None:
    """AI mode ``local`` with the promoted Tier T and Tier S models (spec §9, §10)."""
    config = tmp_path / "hatch-config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "ai_setup_intent.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "ai_mode": "local",
                "local_primary_model": "qwen3.5-4b-q4km-primary",
                "local_triage_model": "qwen3.5-0.8b-q8-triage",
            }
        ),
        encoding="utf-8",
    )
    (config / "ai_runtime.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ai_mode": "local",
                "quality_mode": "local",
                "primary_model_id": "qwen3.5-4b-q4km-primary",
                "triage_model_id": "qwen3.5-0.8b-q8-triage",
                "effective_routing": {"primary": "llm-primary", "triage": "llm-triage"},
                "provider": None,
                "feature_gates": {
                    "cv_tailoring": True,
                    "cover_letter_generation": True,
                    "coach_interview_prep": True,
                },
                "warnings": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(config))
    monkeypatch.setattr(settings, "HATCH_COACH_READINESS_ENABLED", True)


def chat_completion(content: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-synthetic",
        "object": "chat.completion",
        "created": 0,
        "model": "synthetic-local",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80},
    }


def fake_llama(httpx_mock, *, delay: float = 0.0, tips: list[str] | None = None) -> None:
    """Register the local model server double. Health or model probes answer 200."""
    body = json.dumps({"tips": tips if tips is not None else TIPS})

    async def completion(request: httpx.Request) -> httpx.Response:
        if delay:
            await asyncio.sleep(delay)
        return httpx.Response(200, json=chat_completion(body))

    httpx_mock.add_callback(
        completion,
        method="POST",
        url=CHAT_COMPLETIONS,
        is_reusable=True,
        is_optional=True,
    )
    httpx_mock.add_response(
        method="GET",
        url=re.compile(r".*"),
        json={"status": "ok", "data": []},
        is_reusable=True,
        is_optional=True,
    )


def model_dispatches(httpx_mock) -> list[httpx.Request]:
    """Every request that reached the model server, SDK retries included."""
    return [
        request
        for request in httpx_mock.get_requests()
        if request.method == "POST" and CHAT_COMPLETIONS.match(str(request.url))
    ]


def readiness_app(factory) -> FastAPI:
    from app.routers.coach_readiness import router

    app = FastAPI()
    app.include_router(router)

    async def request_db():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = request_db
    return app


def client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def explained_fingerprint(client: httpx.AsyncClient) -> str:
    """Fingerprint of the seeded pattern whose Why? has stored report excerpts."""
    response = await client.get(f"{READINESS}/patterns", params={"include_stale": "true"})
    assert response.status_code == 200, response.text
    for group in response.json()["groups"]:
        for pattern in group["patterns"]:
            if pattern["dimension"] == EXPLAINED_DIMENSION and not pattern.get("stale"):
                why = await client.get(f"{READINESS}/patterns/{pattern['fingerprint']}/why")
                assert why.status_code == 200, why.text
                assert why.json()["excerpts"], "seeded pattern has no Why? excerpts"
                return pattern["fingerprint"]
    raise AssertionError("seeded sessions did not produce the explained pattern")


async def request_tips(client: httpx.AsyncClient, fingerprint: str) -> httpx.Response:
    return await client.post(f"{READINESS}/patterns/{fingerprint}/tips")


async def wait_for_operation(
    client: httpx.AsyncClient, operation_id: str, *, timeout: float = 10.0
) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        response = await client.get(f"{READINESS}/operations/{operation_id}")
        assert response.status_code == 200, response.text
        payload = response.json()
        if payload["status"] in TERMINAL:
            return payload
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"operation still {payload['status']} after {timeout}s")
        await asyncio.sleep(0.05)


async def derived_count(factory, *, kind: str | None = None, source_id: str | None = None) -> int:
    """Durable coach_derived_text rows (spec §11), optionally citing one source."""
    query = "SELECT count(DISTINCT t.id) FROM coach_derived_text t"
    params: dict[str, Any] = {}
    clauses = []
    if source_id is not None:
        query += " JOIN coach_derived_sources s ON s.derived_text_id = t.id"
        clauses.append("s.source_id = :source_id")
        params["source_id"] = source_id
    if kind is not None:
        clauses.append("t.kind = :kind")
        params["kind"] = kind
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    async with factory() as db:
        return int((await db.execute(text(query), params)).scalar_one())


async def insert_derived_text(
    factory,
    *,
    text_id: str,
    kind: str,
    sources: list[tuple[str, str, str]],
) -> None:
    """Seed one cached model output and its sources with the §11 columns only."""
    async with factory() as db:
        await db.execute(
            text(
                "INSERT INTO coach_derived_text "
                "(id, kind, cache_key, text_json, model_identity, prompt_version, created_at) "
                "VALUES (:id, :kind, :cache_key, :text_json, 'synthetic-model', 'v1', :created_at)"
            ),
            {
                "id": text_id,
                "kind": kind,
                "cache_key": f"cache-{text_id}",
                "text_json": json.dumps({"tips": ["Synthetic cached tip."]}),
                "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
            },
        )
        for source_kind, source_id, version in sources:
            await db.execute(
                text(
                    "INSERT INTO coach_derived_sources "
                    "(derived_text_id, source_kind, source_id, source_version) "
                    "VALUES (:text_id, :kind, :source_id, :version)"
                ),
                {
                    "text_id": text_id,
                    "kind": source_kind,
                    "source_id": source_id,
                    "version": version,
                },
            )
        await db.commit()
