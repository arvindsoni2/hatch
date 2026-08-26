"""Exact-payload, durable approval contracts using only synthetic metadata."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.runtime.workflow.approvals import (
    CANONICAL_JSON_SHA256_V1,
    ApprovalManager,
    canonical_payload_hash,
)
from app.runtime.events.models import RuntimeEventRecord, RuntimeOutboxRecord
from app.runtime.workflow.models import ApprovalRecord, ApprovalStatus
from workflow_test_support import start_and_claim


async def test_approval_for_payload_a_does_not_authorize_b(workflow_runtime) -> None:
    """Would fail if validity ignored the durable exact canonical payload digest."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    run, claim = await start_and_claim(kernel, now=now)
    approvals = ApprovalManager(factory, clock=lambda: now)
    record = await approvals.request(
        workflow_run_id=run.id,
        task_attempt_id=claim.task_attempt_id,
        capability_id="artifact.publish",
        payload={"path": "A"},
    )
    assert await approvals.decide(
        record.id, decided_by="synthetic-user", approved=True, now=now
    )
    assert await approvals.is_valid(
        record.id,
        workflow_run_id=run.id,
        workflow_step_id=(await _step_id(factory, claim.task_attempt_id)),
        task_attempt_id=claim.task_attempt_id,
        capability_id="artifact.publish",
        payload={"path": "A"},
        now=now,
    )
    assert not await approvals.is_valid(
        record.id,
        workflow_run_id=run.id,
        workflow_step_id=(await _step_id(factory, claim.task_attempt_id)),
        task_attempt_id=claim.task_attempt_id,
        capability_id="artifact.publish",
        payload={"path": "B"},
        now=now,
    )


async def test_exact_payload_algorithm_and_expiry_bind_approval(workflow_runtime) -> None:
    """Would fail if approval validity accepted a changed payload, algorithm, or expiry."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1, 10)
    run, claim = await start_and_claim(kernel, now=now)
    approvals = ApprovalManager(factory, clock=lambda: now)
    record = await approvals.request(
        workflow_run_id=run.id,
        task_attempt_id=claim.task_attempt_id,
        capability_id="artifact.publish",
        payload={"path": "A", "options": {"dry_run": True}},
        expires_at=now + timedelta(minutes=5),
    )
    assert await approvals.decide(
        record.id, decided_by="synthetic-user", approved=True, now=now
    )
    assert await approvals.is_valid(
        record.id,
        workflow_run_id=run.id,
        workflow_step_id=(await _step_id(factory, claim.task_attempt_id)),
        task_attempt_id=claim.task_attempt_id,
        capability_id="artifact.publish",
        payload={"options": {"dry_run": True}, "path": "A"},
        now=now,
    )
    assert not await approvals.is_valid(
        record.id,
        workflow_run_id=run.id,
        workflow_step_id=(await _step_id(factory, claim.task_attempt_id)),
        task_attempt_id=claim.task_attempt_id,
        capability_id="artifact.publish",
        payload={"path": "B"},
        now=now,
    )
    assert not await approvals.is_valid(
        record.id,
        workflow_run_id=run.id,
        workflow_step_id=(await _step_id(factory, claim.task_attempt_id)),
        task_attempt_id=claim.task_attempt_id,
        capability_id="artifact.delete",
        payload={"path": "A", "options": {"dry_run": True}},
        now=now,
    )
    async with factory.session_factory() as session:
        persisted = await session.get(ApprovalRecord, record.id)
        assert persisted is not None
        persisted.payload_hash_algorithm = "other-v1"
        await session.commit()
    assert not await approvals.is_valid(
        record.id,
        workflow_run_id=run.id,
        workflow_step_id=(await _step_id(factory, claim.task_attempt_id)),
        task_attempt_id=claim.task_attempt_id,
        capability_id="artifact.publish",
        payload={"path": "A", "options": {"dry_run": True}},
        now=now,
    )
    assert not await approvals.is_valid(
        record.id,
        workflow_run_id=run.id,
        workflow_step_id=(await _step_id(factory, claim.task_attempt_id)),
        task_attempt_id=claim.task_attempt_id,
        capability_id="artifact.publish",
        payload={"path": "A"},
        now=now + timedelta(minutes=5),
    )


def test_canonical_payload_hash_is_utf8_order_independent_and_rejects_non_json() -> None:
    """Would fail if canonical serialization changed bytes or admitted NaN values."""
    assert CANONICAL_JSON_SHA256_V1 == "sha256-canonical-json-v1"
    assert canonical_payload_hash({"label": "£", "a": [2, 1]}) == canonical_payload_hash(
        {"a": [2, 1], "label": "£"}
    )
    with pytest.raises(ValueError, match="finite JSON numbers"):
        canonical_payload_hash({"not_a_number": float("nan")})
    with pytest.raises(ValueError, match="algorithm"):
        canonical_payload_hash({"path": "A"}, algorithm="sha1")


def test_canonical_payload_hash_rejects_key_and_sequence_type_collisions() -> None:
    """Would fail if non-JSON types serialized into a different payload authority."""
    assert canonical_payload_hash({"a": [2, 1], "label": "£"}) == (
        "04437b86df2b3b2c80f2aca08cbf88bc63133d27f61b490c5a7c6229052826a1"
    )
    with pytest.raises(ValueError, match="keys must be strings"):
        canonical_payload_hash({1: "A"})  # type: ignore[dict-item]
    with pytest.raises(ValueError, match="list"):
        canonical_payload_hash({"items": ("A",)})


async def _step_id(factory, attempt_id: str) -> str:
    async with factory.session_factory() as session:
        attempt = await session.get(__import__("app.runtime.workflow.models", fromlist=["TaskAttemptRecord"]).TaskAttemptRecord, attempt_id)
        assert attempt is not None
        return attempt.workflow_step_id


async def test_approval_id_is_not_authority_across_run_step_or_attempt(workflow_runtime) -> None:
    """Would fail if approval IDs could be replayed outside their durable exact scope."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    run_a, claim_a = await start_and_claim(kernel, now=now)
    run_b, claim_b = await start_and_claim(kernel, now=now)
    approvals = ApprovalManager(factory, clock=lambda: now)
    record = await approvals.request(
        workflow_run_id=run_a.id,
        task_attempt_id=claim_a.task_attempt_id,
        capability_id="artifact.publish",
        payload={"path": "A"},
    )
    assert await approvals.decide(record.id, decided_by="synthetic-user", approved=True, now=now)
    step_a = await _step_id(factory, claim_a.task_attempt_id)
    step_b = await _step_id(factory, claim_b.task_attempt_id)
    assert await approvals.is_valid(record.id, workflow_run_id=run_a.id, workflow_step_id=step_a, task_attempt_id=claim_a.task_attempt_id, capability_id="artifact.publish", payload={"path": "A"}, now=now)
    assert not await approvals.is_valid(record.id, workflow_run_id=run_b.id, workflow_step_id=step_b, task_attempt_id=claim_b.task_attempt_id, capability_id="artifact.publish", payload={"path": "A"}, now=now)
    assert not await approvals.is_valid(record.id, workflow_run_id=run_a.id, workflow_step_id=step_a, task_attempt_id=claim_b.task_attempt_id, capability_id="artifact.publish", payload={"path": "A"}, now=now)


@pytest.mark.parametrize("canary", ["synthetic transcript content", "synthetic CV content", "prompt-injection", "/tmp/private-path", "model-output"])
async def test_decision_reason_rejects_content_canaries_at_public_and_store_boundaries(workflow_runtime, canary: str) -> None:
    """Would fail if free-text decision metadata could leak into durable approval state."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    run, claim = await start_and_claim(kernel, now=now)
    approvals = ApprovalManager(factory, clock=lambda: now)
    record = await approvals.request(workflow_run_id=run.id, task_attempt_id=claim.task_attempt_id, capability_id="artifact.publish", payload={"path": "A"})
    with pytest.raises(ValueError, match="stable code"):
        await approvals.decide(record.id, decided_by="synthetic-user", approved=True, reason=canary, now=now)
    async with factory.transaction() as uow:
        with pytest.raises(ValueError, match="stable code"):
            await uow.approvals.decide(record.id, status=ApprovalStatus.APPROVED, decided_by="synthetic-user", decision_reason=canary, decided_at=now)


async def test_approval_decision_and_event_roll_back_together_on_injected_failure(workflow_runtime) -> None:
    """Would fail if approval state committed without its required metadata event."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    run, claim = await start_and_claim(kernel, now=now)
    approvals = ApprovalManager(factory, clock=lambda: now, fail_after_state_change=True)
    record = await approvals.request(workflow_run_id=run.id, task_attempt_id=claim.task_attempt_id, capability_id="artifact.publish", payload={"path": "A"})
    with pytest.raises(RuntimeError, match="approval_state_change"):
        await approvals.decide(record.id, decided_by="synthetic-user", approved=True, now=now)
    async with factory.session_factory() as session:
        persisted = await session.get(ApprovalRecord, record.id)
        events = list((await session.scalars(select(RuntimeEventRecord))).all())
    assert persisted is not None and persisted.status == ApprovalStatus.PENDING
    assert [event.event_type for event in events] == ["approval.requested"]


async def test_request_rejects_misaligned_scope_without_creating_record(workflow_runtime) -> None:
    """Would fail if an approval could be attached to an unrelated run/attempt."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    first_run, first_claim = await start_and_claim(kernel, now=now)
    second_run, _ = await start_and_claim(kernel, now=now)
    approvals = ApprovalManager(factory, clock=lambda: now)

    with pytest.raises(ValueError, match="scope"):
        await approvals.request(
            workflow_run_id=second_run.id,
            task_attempt_id=first_claim.task_attempt_id,
            capability_id="artifact.publish",
            payload={"path": "A"},
        )
    async with factory.session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(ApprovalRecord))
    assert count == 0


async def test_decision_is_one_shot_expiry_aware_and_race_safe(workflow_runtime) -> None:
    """Would fail if duplicate/expired decisions could overwrite an approval."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    run, claim = await start_and_claim(kernel, now=now)
    approvals = ApprovalManager(factory, clock=lambda: now)
    record = await approvals.request(
        workflow_run_id=run.id,
        task_attempt_id=claim.task_attempt_id,
        capability_id="artifact.publish",
        payload={"path": "A"},
    )
    outcomes = await asyncio.gather(
        approvals.decide(record.id, decided_by="user-a", approved=True, now=now),
        approvals.decide(record.id, decided_by="user-b", approved=False, now=now),
    )
    assert sorted(outcomes) == [False, True]
    assert not await approvals.decide(
        record.id, decided_by="user-c", approved=True, now=now
    )

    expired = await approvals.request(
        workflow_run_id=run.id,
        task_attempt_id=claim.task_attempt_id,
        capability_id="artifact.publish",
        payload={"path": "expired"},
        expires_at=now + timedelta(seconds=1),
    )
    assert not await approvals.decide(
        expired.id,
        decided_by="synthetic-user",
        approved=True,
        now=now + timedelta(seconds=1),
    )
    async with factory.session_factory() as session:
        persisted = await session.get(ApprovalRecord, expired.id)
    assert persisted is not None
    assert persisted.status == ApprovalStatus.EXPIRED


async def test_payload_change_invalidates_pending_and_approved_records_after_restart(workflow_runtime) -> None:
    """Would fail if a prior approval survived a changed committing payload or restart."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    run, claim = await start_and_claim(kernel, now=now)
    first_process = ApprovalManager(factory, clock=lambda: now)
    approved = await first_process.request(
        workflow_run_id=run.id,
        task_attempt_id=claim.task_attempt_id,
        capability_id="artifact.publish",
        payload={"path": "A"},
    )
    pending = await first_process.request(
        workflow_run_id=run.id,
        task_attempt_id=claim.task_attempt_id,
        capability_id="artifact.publish",
        payload={"path": "A", "variant": 2},
    )
    assert await first_process.decide(
        approved.id, decided_by="synthetic-user", approved=True, now=now
    )

    restarted = ApprovalManager(factory, clock=lambda: now + timedelta(seconds=1))
    assert (
        await restarted.invalidate_for_payload_change(
            claim.task_attempt_id, {"path": "B"}, now=now + timedelta(seconds=1)
        )
        == 2
    )
    assert not await restarted.is_valid(
        approved.id,
        workflow_run_id=run.id,
        workflow_step_id=(await _step_id(factory, claim.task_attempt_id)),
        task_attempt_id=claim.task_attempt_id,
        capability_id="artifact.publish",
        payload={"path": "A"},
        now=now,
    )
    async with factory.session_factory() as session:
        rows = list(
            (
                await session.scalars(
                    select(ApprovalRecord).where(
                        ApprovalRecord.id.in_([approved.id, pending.id])
                    )
                )
            ).all()
        )
    assert {row.status for row in rows} == {ApprovalStatus.INVALIDATED}


@pytest.mark.parametrize("value", ["", " ", "x" * 129, "bad\nactor"])
async def test_approval_identifiers_and_decision_metadata_are_bounded(workflow_runtime, value: str) -> None:
    """Would fail if unbounded or control-character metadata entered durable approvals."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    run, claim = await start_and_claim(kernel, now=now)
    approvals = ApprovalManager(factory, clock=lambda: now)
    with pytest.raises(ValueError):
        await approvals.request(
            workflow_run_id=run.id,
            task_attempt_id=claim.task_attempt_id,
            capability_id=value,
            payload={"path": "A"},
        )


async def test_invalid_decision_metadata_leaves_approval_pending(workflow_runtime) -> None:
    """Would fail if a bad actor or reason changed the durable approval state."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    run, claim = await start_and_claim(kernel, now=now)
    approvals = ApprovalManager(factory, clock=lambda: now)
    record = await approvals.request(
        workflow_run_id=run.id,
        task_attempt_id=claim.task_attempt_id,
        capability_id="artifact.publish",
        payload={"path": "A"},
    )
    with pytest.raises(ValueError):
        await approvals.decide(
            record.id, decided_by="bad\nactor", approved=True, now=now
        )
    with pytest.raises(ValueError):
        await approvals.decide(
            record.id,
            decided_by="synthetic-user",
            approved=True,
            reason="bad\nreason",
            now=now,
        )
    async with factory.session_factory() as session:
        persisted = await session.get(ApprovalRecord, record.id)
    assert persisted is not None
    assert persisted.status == ApprovalStatus.PENDING


async def test_store_rejects_unsafe_actor_and_unregistered_reason_code(workflow_runtime) -> None:
    """Would fail if direct storage writes bypassed the approval privacy boundary."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    run, claim = await start_and_claim(kernel, now=now)
    approvals = ApprovalManager(factory, clock=lambda: now)
    record = await approvals.request(
        workflow_run_id=run.id,
        task_attempt_id=claim.task_attempt_id,
        capability_id="artifact.publish",
        payload={"path": "A"},
    )
    async with factory.transaction() as uow:
        with pytest.raises(ValueError, match="safe identifier"):
            await uow.approvals.decide(
                record.id,
                status=ApprovalStatus.APPROVED,
                decided_by="synthetic\nuser",
                decision_reason="granted",
                decided_at=now,
            )
        with pytest.raises(ValueError, match="stable code"):
            await uow.approvals.decide(
                record.id,
                status=ApprovalStatus.APPROVED,
                decided_by="synthetic-user",
                decision_reason="prompt-injection",
                decided_at=now,
            )


async def test_each_approval_transition_appends_one_metadata_event_without_outbox(
    workflow_runtime,
) -> None:
    """Would fail if an approval transition diverged from its ARCH-08 event."""
    kernel, factory = workflow_runtime
    now = datetime(2030, 1, 1)
    run, claim = await start_and_claim(kernel, now=now)
    approvals = ApprovalManager(factory, clock=lambda: now)
    granted = await approvals.request(
        workflow_run_id=run.id,
        task_attempt_id=claim.task_attempt_id,
        capability_id="artifact.publish",
        payload={"path": "grant"},
    )
    denied = await approvals.request(
        workflow_run_id=run.id,
        task_attempt_id=claim.task_attempt_id,
        capability_id="artifact.publish",
        payload={"path": "deny"},
    )
    expired = await approvals.request(
        workflow_run_id=run.id,
        task_attempt_id=claim.task_attempt_id,
        capability_id="artifact.publish",
        payload={"path": "expire"},
        expires_at=now + timedelta(seconds=1),
    )
    await approvals.request(
        workflow_run_id=run.id,
        task_attempt_id=claim.task_attempt_id,
        capability_id="artifact.publish",
        payload={"path": "invalidate"},
    )
    assert await approvals.decide(
        granted.id, decided_by="synthetic-user", approved=True, now=now
    )
    assert await approvals.decide(
        denied.id, decided_by="synthetic-user", approved=False, now=now
    )
    assert not await approvals.decide(
        expired.id,
        decided_by="synthetic-user",
        approved=True,
        now=now + timedelta(seconds=1),
    )
    assert await approvals.invalidate_for_payload_change(
        claim.task_attempt_id, {"path": "changed"}, now=now + timedelta(seconds=2)
    ) == 2
    async with factory.session_factory() as session:
        events = list((await session.scalars(select(RuntimeEventRecord))).all())
        outbox_count = await session.scalar(select(func.count()).select_from(RuntimeOutboxRecord))
    event_types = [event.event_type for event in events]
    assert event_types.count("approval.requested") == 4
    assert event_types.count("approval.granted") == 1
    assert event_types.count("approval.denied") == 1
    assert event_types.count("approval.expired") == 1
    assert event_types.count("approval.invalidated") == 2
    assert all(event.sensitivity == "metadata" for event in events)
    assert outbox_count == 0
