"""Canary tests for metadata-only durable runtime records."""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.runtime.evaluation.models import (
    EvaluationRunRecord,
    EvidenceObservationRecord,
    ShadowComparisonRecord,
    ValidationResultRecord,
)
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


async def test_evaluation_store_rejects_opaque_model_output(privacy_factory) -> None:
    async with privacy_factory.transaction() as uow:
        run = await uow.workflows.create_run(
            workflow_definition_id="synthetic.evaluate",
            workflow_definition_version=1,
            domain_type="synthetic",
            runtime_mode="legacy",
            max_attempts=1,
        )
        step = await uow.workflows.create_step(
            workflow_run_id=run.id,
            step_key="evaluate",
            step_order=1,
            task_id="synthetic.evaluate",
            task_version=1,
        )
        attempt = await uow.workflows.create_attempt(
            workflow_step_id=step.id,
            attempt_number=1,
        )
        with pytest.raises(MetadataOnlyViolation):
            await uow.evaluations.record_evaluation(
                task_attempt_id=attempt.id,
                evaluator_id="synthetic.model",
                evaluator_version=1,
                evaluator_type="model",
                evaluation_spec_id="synthetic.spec",
                evaluation_spec_version=1,
                status="completed",
                result="passed",
                result_json={"answer": "MODEL-OUTPUT-CANARY"},
            )


async def _create_attempt(privacy_factory) -> str:
    async with privacy_factory.transaction() as uow:
        run = await uow.workflows.create_run(
            workflow_definition_id="synthetic.evaluate",
            workflow_definition_version=1,
            domain_type="synthetic",
            runtime_mode="new",
            max_attempts=1,
        )
        step = await uow.workflows.create_step(
            workflow_run_id=run.id,
            step_key="evaluate",
            step_order=1,
            task_id="synthetic.evaluate",
            task_version=1,
        )
        attempt = await uow.workflows.create_attempt(
            workflow_step_id=step.id,
            attempt_number=1,
        )
        await uow.commit()
        return attempt.id


@pytest.mark.parametrize(
    ("record_type", "field", "canary"),
    [
        ("evaluation", "evaluator_id", "TRANSCRIPT-CANARY"),
        ("evaluation", "evaluator_model_version", "/home/user/resume.txt"),
        ("evaluation", "reason_codes_json", ["MODEL-OUTPUT-CANARY"]),
        ("evaluation", "scores_json", {"quality": "CV-CANARY"}),
        ("validation", "validator_id", "PROMPT-CANARY"),
        ("validation", "metrics_json", {"detail": "secret-token"}),
        ("observation", "source_ref", "/tmp/user-transcript.txt"),
        ("observation", "observation_json", {"evidence": "MODEL-OUTPUT-CANARY"}),
    ],
)
async def test_metadata_only_records_reject_sensitive_canaries(
    privacy_factory, record_type: str, field: str, canary: object
) -> None:
    attempt_id = await _create_attempt(privacy_factory)
    values: dict[str, object]
    if record_type == "evaluation":
        values = {
            "task_attempt_id": attempt_id,
            "evaluator_id": "synthetic.evaluator",
            "evaluator_version": 1,
            "evaluator_type": "deterministic",
            "evaluation_spec_id": "synthetic.spec",
            "evaluation_spec_version": 1,
            "status": "completed",
            "result": "passed",
            "reason_codes_json": ["schema_valid"],
            "scores_json": {"quality": 1.0},
            field: canary,
        }
        method = "record_evaluation"
    elif record_type == "validation":
        values = {
            "task_attempt_id": attempt_id,
            "validator_id": "synthetic.validator",
            "validator_version": 1,
            "status": "passed",
            "reason_codes_json": ["schema_valid"],
            "metrics_json": {"schema_errors": 0},
            field: canary,
        }
        method = "record_validation"
    else:
        values = {
            "evaluation_run_id": "evaluation-id",
            "evidence_type": "synthetic",
            "source_ref": "sha256:abc",
            "observation_json": {"sample_size": 1},
            field: canary,
        }
        method = "record_observation"

    with pytest.raises((MetadataOnlyViolation, ValueError)):
        async with privacy_factory.transaction() as uow:
            await getattr(uow.evaluations, method)(**values)

    async with privacy_factory.session_factory() as session:
        assert list((await session.scalars(select(EvaluationRunRecord))).all()) == []
        assert list((await session.scalars(select(ValidationResultRecord))).all()) == []
        assert (
            list((await session.scalars(select(EvidenceObservationRecord))).all()) == []
        )


async def test_typed_evaluation_and_validation_metadata_can_commit(
    privacy_factory,
) -> None:
    attempt_id = await _create_attempt(privacy_factory)
    async with privacy_factory.transaction() as uow:
        await uow.evaluations.record_validation(
            task_attempt_id=attempt_id,
            validator_id="synthetic.schema",
            validator_version=1,
            status="passed",
            reason_codes_json=["schema_valid"],
            metrics_json={"schema_errors": 0},
        )
        await uow.evaluations.record_evaluation(
            task_attempt_id=attempt_id,
            evaluator_id="synthetic.evaluator",
            evaluator_version=1,
            evaluator_type="deterministic",
            evaluation_spec_id="synthetic.spec",
            evaluation_spec_version=1,
            status="completed",
            result="passed",
            reason_codes_json=["schema_valid"],
            scores_json={"quality": 0.9},
            validation_metrics_json={"schema_errors": 0},
        )
        await uow.commit()

    async with privacy_factory.session_factory() as session:
        assert (
            len(list((await session.scalars(select(EvaluationRunRecord))).all())) == 1
        )
        assert (
            len(list((await session.scalars(select(ValidationResultRecord))).all()))
            == 1
        )


@pytest.mark.parametrize("policy", ("metadata_only", "redacted", "disabled"))
def test_llm_trace_buffer_never_retains_response_preview_in_normal_capture_modes(
    monkeypatch, policy: str
) -> None:
    from app.agents.tools import llm_factory

    canary = "MODEL-OUTPUT-CANARY"
    monkeypatch.setenv("HATCH_RUNTIME_CAPTURE_POLICY", policy)
    llm_factory.clear_llm_traces()
    llm_factory.record_trace("synthetic-model", 1, canary)

    traces = llm_factory.get_llm_traces()
    assert canary not in json.dumps(traces)
    assert traces[0]["response_preview"] == ""


def test_runtime_capture_policy_defaults_and_rejects_debug_content(
    monkeypatch,
) -> None:
    from pydantic import ValidationError

    from app.config import Settings
    from app.runtime.control import CapturePolicy

    assert (
        Settings(_env_file=None).HATCH_RUNTIME_CAPTURE_POLICY
        is CapturePolicy.METADATA_ONLY
    )
    monkeypatch.setenv("HATCH_RUNTIME_CAPTURE_POLICY", "debug_content")
    with pytest.raises(ValidationError, match="runtime_capture_policy_not_allowed"):
        Settings(_env_file=None)
