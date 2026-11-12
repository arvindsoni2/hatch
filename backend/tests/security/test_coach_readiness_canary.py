"""RED contract for P6: content canary (spec §10 common rules, §15 canary).

Written by Claude Code before implementation (plan §1.5). A unique string is put
in synthetic report excerpts, transcripts and a story. A real tips request runs
through the readiness router and runtime; only the local model server is faked,
at HTTP. The canary must reach the model prompt and nowhere else: not in runtime
records or events (any table other than the seeded product tables), traces or logs.
"""
from __future__ import annotations

import json
import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker

sys.path.insert(0, str(Path(__file__).parents[1] / "integration"))

from app import database  # noqa: E402
from app.agents.tools import llm_factory  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import Base, create_sqlite_engine  # noqa: E402
from app.models.story import Story  # noqa: E402
from app.observability import runtime as telemetry  # noqa: E402
from app.repositories.coach_readiness_repository import CoachReadinessRepository  # noqa: E402
from app.services import coach_reconciliation  # noqa: E402
from app.services.coach_readiness.privacy import ReadinessPrivacy  # noqa: E402
from app.services.source_events import register_listener, unregister_listener  # noqa: E402
from coach_readiness_support import (  # noqa: E402
    client_for,
    configure_local_ai,
    fake_llama,
    model_dispatches,
    not_the_test_client,
    readiness_app,
    request_tips,
    seed_pattern_sessions,
    explained_fingerprint,
    wait_for_operation,
)

CANARY = "P6-CANARY-ORCHID-4471"
# Product tables the test itself writes the canary into.
SEEDED_TABLES = {"interview_sessions", "session_recordings", "stories"}


@pytest_asyncio.fixture
async def factory(tmp_path, monkeypatch):
    engine = create_sqlite_engine(f"sqlite+aiosqlite:///{tmp_path / 'canary.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(coach_reconciliation, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(settings, "HATCH_COACH_MEDIA_ROOT", str(tmp_path / "media"))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield session_factory
    finally:
        await engine.dispose()


class _Recorder:
    """Telemetry sink double: keeps every span name, attribute, event and metric label."""

    def __init__(self) -> None:
        self.items: list[Any] = []

    # tracer
    @contextmanager
    def start_as_current_span(self, name, **options):
        self.items.append(name)
        self.items.append(options.get("attributes"))
        yield self

    def set_attribute(self, key, value) -> None:
        self.items.append((key, value))

    def add_event(self, name, attributes=None) -> None:
        self.items.append((name, attributes))

    def set_status(self, *args, **kwargs) -> None:
        self.items.append(args)

    # meter
    def create_histogram(self, name, **kwargs):
        return self

    def create_counter(self, name, **kwargs):
        return self

    def record(self, value, attributes=None) -> None:
        self.items.append(attributes)

    def add(self, value, attributes=None) -> None:
        self.items.append(attributes)


async def _tables_containing(factory, needle: str) -> set[str]:
    found: set[str] = set()
    async with factory() as db:
        names = await db.run_sync(lambda sync: inspect(sync.connection()).get_table_names())
        for name in names:
            rows = (await db.execute(text(f'SELECT * FROM "{name}"'))).all()
            if any(needle in json.dumps(list(row), default=str) for row in rows):
                found.add(name)
    return found


@pytest.mark.httpx_mock(should_mock=not_the_test_client)
async def test_content_canary_absent_from_runtime_records_events_logs(
    factory, httpx_mock, tmp_path, monkeypatch, caplog
) -> None:
    configure_local_ai(tmp_path, monkeypatch)
    fake_llama(httpx_mock)
    recorder = _Recorder()
    monkeypatch.setattr(
        telemetry,
        "_runtime",
        telemetry.TelemetryRuntime(status="active", tracer=recorder, meter=recorder),
    )
    llm_factory.clear_llm_traces()
    listener = ReadinessPrivacy(CoachReadinessRepository(factory))
    register_listener(listener)
    try:
        await seed_pattern_sessions(factory, canary=CANARY)
        async with factory() as db:
            db.add(
                Story(
                    id="canary-story", title="Synthetic canary story", slug="canary-story",
                    situation=f"Synthetic situation {CANARY}", result="Done",
                )
            )
            await db.commit()
        # Capture every log record from here on: the request, runtime and generation.
        caplog.clear()
        caplog.set_level(logging.DEBUG)

        async with client_for(readiness_app(factory)) as client:
            fingerprint = await explained_fingerprint(client)
            response = await request_tips(client, fingerprint)
            assert response.status_code == 202, response.text
            finished = await wait_for_operation(client, response.json()["operation_id"])
            assert finished["status"] == "succeeded"
            assert CANARY not in json.dumps(finished)
    finally:
        unregister_listener(listener)

    # The content did reach the model, so its absence elsewhere is meaningful.
    dispatches = model_dispatches(httpx_mock)
    assert len(dispatches) == 1
    assert CANARY in dispatches[0].content.decode("utf-8")

    assert await _tables_containing(factory, CANARY) <= SEEDED_TABLES
    assert CANARY not in caplog.text
    assert all(CANARY not in record.getMessage() for record in caplog.records)
    assert CANARY not in json.dumps(recorder.items, default=str)
    assert CANARY not in json.dumps(llm_factory.get_llm_traces(), default=str)
