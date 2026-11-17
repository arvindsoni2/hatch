"""P6 runtime binding: one repair, deadline, AI-off, degradation and reasoning strip."""
from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import database
from app.config import settings
from app.database import Base, create_sqlite_engine
from app.services import coach_reconciliation
from app.services.coach_readiness import explain
from app.services.coach_readiness import tiers

sys.path.insert(0, str(Path(__file__).parents[1] / "integration"))


from coach_readiness_support import (  # noqa: E402
    CHAT_COMPLETIONS,
    TIPS,
    chat_completion,
    client_for,
    configure_local_ai,
    explained_fingerprint,
    fake_llama,
    model_dispatches,
    not_the_test_client,
    readiness_app,
    request_tips,
    seed_pattern_sessions,
    wait_for_operation,
)

@pytest_asyncio.fixture
async def coach_database(tmp_path, monkeypatch):
    engine = create_sqlite_engine(f"sqlite+aiosqlite:///{tmp_path / 'coach.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "AsyncSessionLocal", factory)
    monkeypatch.setattr(coach_reconciliation, "AsyncSessionLocal", factory)
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", str(tmp_path / "media"))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.httpx_mock(should_mock=not_the_test_client)
async def test_one_generation_plus_one_repair_max(
    coach_database, httpx_mock, tmp_path, monkeypatch
) -> None:
    configure_local_ai(tmp_path, monkeypatch)
    calls = {"count": 0}

    async def completion(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        tips = ["bad", "bad", "bad", "bad"] if calls["count"] == 1 else TIPS
        return httpx.Response(200, json=chat_completion(json.dumps({"tips": tips})))

    httpx_mock.add_callback(
        completion, method="POST", url=CHAT_COMPLETIONS, is_reusable=True, is_optional=True
    )
    await seed_pattern_sessions(coach_database)

    async with client_for(readiness_app(coach_database)) as client:
        fingerprint = await explained_fingerprint(client)
        response = await request_tips(client, fingerprint)
        assert response.status_code == 202, response.text
        finished = await wait_for_operation(client, response.json()["operation_id"])

    assert finished["status"] == "succeeded"
    assert len(model_dispatches(httpx_mock)) == 2


@pytest.mark.httpx_mock(should_mock=not_the_test_client)
async def test_deadline_absolute_across_repair_including_queue(
    coach_database, httpx_mock, tmp_path, monkeypatch
) -> None:
    configure_local_ai(tmp_path, monkeypatch)
    real = tiers.load_tier_map()
    monkeypatch.setattr(
        explain, "load_tier_map", lambda: {**real, "S": replace(real["S"], deadline_s=1)}
    )
    fake_llama(httpx_mock, delay=2.0)
    await seed_pattern_sessions(coach_database)

    started = time.monotonic()
    async with client_for(readiness_app(coach_database)) as client:
        fingerprint = await explained_fingerprint(client)
        response = await request_tips(client, fingerprint)
        finished = await wait_for_operation(client, response.json()["operation_id"])
    elapsed = time.monotonic() - started

    assert finished["status"] == "degraded"
    assert elapsed < 2.5


async def test_ai_mode_none_creates_no_requests(
    coach_database, httpx_mock, tmp_path, monkeypatch
) -> None:
    config = tmp_path / "ai-none"
    config.mkdir()
    (config / "ai_runtime.json").write_text(
        json.dumps({"schema_version": 1, "ai_mode": "none", "feature_gates": {}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(config))
    monkeypatch.setattr(settings, "HATCH_COACH_READINESS_ENABLED", True)
    fake_llama(httpx_mock)
    await seed_pattern_sessions(coach_database)

    async with client_for(readiness_app(coach_database)) as client:
        fingerprint = await explained_fingerprint(client)
        response = await request_tips(client, fingerprint)

    assert response.status_code == 200
    assert response.json()["tips"] == []
    assert model_dispatches(httpx_mock) == []


async def test_route_unavailable_degrades_within_1s(
    coach_database, tmp_path, monkeypatch
) -> None:
    configure_local_ai(tmp_path, monkeypatch)

    async def unavailable(_context):
        raise RuntimeError("route unavailable")

    monkeypatch.setattr(explain, "_call_model", unavailable)
    await seed_pattern_sessions(coach_database)

    started = time.monotonic()
    async with client_for(readiness_app(coach_database)) as client:
        fingerprint = await explained_fingerprint(client)
        response = await request_tips(client, fingerprint)
        finished = await wait_for_operation(client, response.json()["operation_id"])
    elapsed = time.monotonic() - started

    assert finished["status"] == "degraded"
    assert elapsed < 1.0


@pytest.mark.httpx_mock(should_mock=not_the_test_client)
async def test_thinking_text_stripped_from_output(
    coach_database, httpx_mock, tmp_path, monkeypatch
) -> None:
    configure_local_ai(tmp_path, monkeypatch)
    content = f"<thinking>private reasoning</thinking>{json.dumps({'tips': TIPS})}"

    async def completion(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=chat_completion(content))

    httpx_mock.add_callback(
        completion, method="POST", url=CHAT_COMPLETIONS, is_reusable=True, is_optional=True
    )
    await seed_pattern_sessions(coach_database)

    async with client_for(readiness_app(coach_database)) as client:
        fingerprint = await explained_fingerprint(client)
        response = await request_tips(client, fingerprint)
        finished = await wait_for_operation(client, response.json()["operation_id"])
        cached = await request_tips(client, fingerprint)

    assert finished["status"] == "succeeded"
    assert cached.status_code == 200
    assert cached.json()["tips"] == TIPS
    assert "thinking" not in cached.text.casefold()
