"""Canary tests for metadata-only durable runtime records."""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.runtime.evaluation.models import ShadowComparisonRecord
from app.runtime.events.models import RuntimeEventRecord
from app.runtime.events.repository import MetadataOnlyViolation
from app.runtime.storage.sqlite import SQLiteRuntimeUnitOfWorkFactory


@pytest_asyncio.fixture
async def privacy_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'privacy.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = SQLiteRuntimeUnitOfWorkFactory(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    ("field", "canary"),
    [
        ("cv_text", "CV-CANARY"),
        ("transcript", "TRANSCRIPT-CANARY"),
        ("prompt", "PROMPT-CANARY"),
        ("file_path", "/tmp/user-file"),
    ],
)
async def test_metadata_only_events_reject_sensitive_canaries(
    privacy_factory, field: str, canary: str
) -> None:
    with pytest.raises(MetadataOnlyViolation):
        async with privacy_factory.transaction() as uow:
            await uow.events.append(
                event_type="runtime.unsafe",
                event_version=1,
                aggregate_type="synthetic",
                aggregate_id="synthetic-1",
                actor_type="system",
                payload_json={field: canary},
                sensitivity="metadata",
            )

    async with privacy_factory.session_factory() as session:
        records = list((await session.scalars(select(RuntimeEventRecord))).all())
    serialized = json.dumps([record.payload_json for record in records])
    assert canary not in serialized


async def test_metadata_only_event_rejects_unknown_alias_and_sensitivity(
    privacy_factory,
) -> None:
    cases = (
        {"payload_json": {"answer": "TRANSCRIPT-CANARY"}, "sensitivity": "metadata"},
        {"payload_json": {"reason_code": "safe"}, "sensitivity": "raw"},
    )
    for values in cases:
        with pytest.raises(MetadataOnlyViolation):
            async with privacy_factory.transaction() as uow:
                await uow.events.append(
                    event_type="runtime.unsafe",
                    event_version=1,
                    aggregate_type="synthetic",
                    aggregate_id="synthetic-1",
                    actor_type="system",
                    **values,
                )


async def test_outbox_error_detail_rejects_sensitive_canary(privacy_factory) -> None:
    async with privacy_factory.transaction() as uow:
        event = await uow.events.append(
            event_type="runtime.safe",
            event_version=1,
            aggregate_type="synthetic",
            aggregate_id="synthetic-1",
            actor_type="system",
            payload_json={"reason_code": "safe"},
            sensitivity="metadata",
        )
        await uow.outbox.enqueue(event.id, "runtime.telemetry")
        await uow.commit()

    from app.runtime.events.outbox import OutboxPublisher

    publisher = OutboxPublisher(privacy_factory.session_factory)
    claim = await publisher.claim_next()
    assert claim is not None
    with pytest.raises(MetadataOnlyViolation):
        await publisher.finalize_delivery(
            claim,
            delivered=False,
            error_code="provider_failure",
            error_detail="TRANSCRIPT-CANARY",
        )


async def test_shadow_store_rejects_raw_metrics(privacy_factory) -> None:
    with pytest.raises(MetadataOnlyViolation):
        async with privacy_factory.transaction() as uow:
            await uow.shadow.record(
                slice_name="synthetic",
                domain_type="synthetic",
                domain_id_hash="sha256:abc",
                legacy_result_hash="sha256:def",
                runtime_result_hash="sha256:ghi",
                comparison_status="different",
                metrics_json={"raw_output": "CV-CANARY"},
            )

    async with privacy_factory.session_factory() as session:
        assert list((await session.scalars(select(ShadowComparisonRecord))).all()) == []
