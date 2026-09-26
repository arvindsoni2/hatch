"""Fenced, at-least-once runtime outbox delivery tests."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.runtime.events.models import RuntimeOutboxAttemptRecord, RuntimeOutboxRecord
from app.runtime.events.outbox import OutboxPublisher
from app.runtime.storage.sqlite import SQLiteRuntimeUnitOfWorkFactory


@pytest_asyncio.fixture
async def outbox_context(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'outbox.db'}",
        connect_args={"timeout": 0.01},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    factory = SQLiteRuntimeUnitOfWorkFactory(session_factory)
    async with factory.transaction() as uow:
        run = await uow.workflows.create_run(
            workflow_definition_id="synthetic.workflow",
            workflow_definition_version=1,
            domain_type="synthetic",
            runtime_mode="new",
        )
        event = await uow.events.append(
            event_type="runtime.run_created",
            event_version=1,
            aggregate_type="workflow_run",
            aggregate_id=run.id,
            workflow_run_id=run.id,
            actor_type="system",
            payload_json={"reason_code": "created"},
            sensitivity="metadata",
        )
        entry = await uow.outbox.enqueue(event.id, "runtime.evaluation")
        await uow.commit()
    try:
        yield session_factory, entry.id, event.id
    finally:
        await engine.dispose()


async def test_outbox_supports_only_declared_destinations(outbox_context) -> None:
    session_factory, _, event_id = outbox_context
    factory = SQLiteRuntimeUnitOfWorkFactory(session_factory)
    with pytest.raises(ValueError, match="unsupported runtime outbox destination"):
        async with factory.transaction() as uow:
            await uow.outbox.enqueue(event_id, "arbitrary.side_effect")


async def test_fenced_delivery_preserves_append_only_attempt_history(
    outbox_context,
) -> None:
    session_factory, entry_id, event_id = outbox_context
    publisher = OutboxPublisher(session_factory, lease_duration=timedelta(seconds=30))
    first = await publisher.claim_next(now=datetime.utcnow())
    assert first is not None
    assert first.entry_id == entry_id
    assert first.event_id == event_id

    assert await publisher.finalize_delivery(
        first, delivered=False, error_code="temporary"
    )
    second = await publisher.claim_next(now=datetime.utcnow() + timedelta(minutes=1))
    assert second is not None
    assert second.event_id == first.event_id
    assert second.fencing_token > first.fencing_token
    assert not await publisher.finalize_delivery(first, delivered=True)
    assert await publisher.finalize_delivery(second, delivered=True)

    async with session_factory() as session:
        entry = await session.get(RuntimeOutboxRecord, entry_id)
        attempts = list(
            (
                await session.scalars(
                    select(RuntimeOutboxAttemptRecord)
                    .where(RuntimeOutboxAttemptRecord.outbox_entry_id == entry_id)
                    .order_by(RuntimeOutboxAttemptRecord.attempt_number)
                )
            ).all()
        )

    assert entry is not None
    assert entry.status == "delivered"
    assert [attempt.attempt_number for attempt in attempts] == [1, 2]
    assert [attempt.result for attempt in attempts] == ["retry_wait", "delivered"]


async def test_claim_retries_short_sqlite_lock_contention(outbox_context) -> None:
    session_factory, entry_id, _ = outbox_context
    database = session_factory.kw["bind"].url.database
    assert database is not None
    lock = sqlite3.connect(database, timeout=0.01)
    lock.execute("BEGIN EXCLUSIVE")
    publisher = OutboxPublisher(
        session_factory,
        lease_duration=timedelta(seconds=30),
        lock_retry_attempts=10,
    )
    task = asyncio.create_task(publisher.claim_next())
    await asyncio.sleep(0.03)
    lock.rollback()
    lock.close()

    claim = await task
    assert claim is not None
    assert claim.entry_id == entry_id


async def test_concurrent_publishers_issue_one_claim(outbox_context) -> None:
    session_factory, entry_id, _ = outbox_context
    publishers = [OutboxPublisher(session_factory), OutboxPublisher(session_factory)]
    claims = await asyncio.gather(*(publisher.claim_next() for publisher in publishers))
    issued = [claim for claim in claims if claim is not None]
    assert len(issued) == 1
    assert issued[0].entry_id == entry_id


async def test_finalize_retries_short_sqlite_lock_contention(outbox_context) -> None:
    session_factory, entry_id, _ = outbox_context
    publisher = OutboxPublisher(session_factory, lock_retry_attempts=10)
    claim = await publisher.claim_next()
    assert claim is not None

    database = session_factory.kw["bind"].url.database
    assert database is not None
    lock = sqlite3.connect(database, timeout=0.01)
    lock.execute("BEGIN EXCLUSIVE")
    task = asyncio.create_task(publisher.finalize_delivery(claim, delivered=True))
    await asyncio.sleep(0.03)
    lock.rollback()
    lock.close()

    assert await task
    async with session_factory() as session:
        entry = await session.get(RuntimeOutboxRecord, entry_id)
    assert entry is not None
    assert entry.status == "delivered"
