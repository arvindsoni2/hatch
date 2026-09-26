"""Payload-bound approval operations backed by the runtime unit of work."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import select

from ..events.models import RuntimeActorType

from .models import (
    ApprovalRecord,
    ApprovalStatus,
    TaskAttemptRecord,
    WorkflowRunRecord,
    WorkflowStepRecord,
)

CANONICAL_JSON_SHA256_V1 = "sha256-canonical-json-v1"
_MAX_CANONICAL_PAYLOAD_BYTES = 64 * 1024
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_STABLE_REASON_CODE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_MAX_REASON_CODE_LENGTH = 128
_APPROVAL_REASON_CODES = frozenset(
    {
        "requested",
        "granted",
        "denied",
        "expired",
        "payload_changed",
        "policy_denied",
        "user_confirmed",
        "user_declined",
    }
)


def canonical_payload_hash(
    payload: Mapping[str, Any],
    algorithm: str = CANONICAL_JSON_SHA256_V1,
) -> str:
    """Hash the exact UTF-8 canonical JSON representation of a safe payload."""
    if algorithm != CANONICAL_JSON_SHA256_V1:
        raise ValueError("unsupported payload hash algorithm")
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    _validate_json_native(payload)
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError("payload must be canonical JSON") from error
    if len(encoded) > _MAX_CANONICAL_PAYLOAD_BYTES:
        raise ValueError("payload exceeds the canonical JSON size limit")
    return hashlib.sha256(encoded).hexdigest()


def _validate_json_native(value: Any, *, path: str = "payload") -> None:
    """Reject Python values whose JSON coercion could change approval authority."""
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"{path} must contain only finite JSON numbers")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} object keys must be strings")
            _validate_json_native(item, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_native(item, path=f"{path}[{index}]")
        return
    if isinstance(value, tuple):
        raise ValueError(f"{path} arrays must be JSON lists")
    raise ValueError(f"{path} must contain only JSON-native values")


def _bounded_identifier(value: object, field: str, *, limit: int = 128) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a bounded safe identifier")
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > limit
        or _SAFE_IDENTIFIER.fullmatch(normalized) is None
    ):
        raise ValueError(f"{field} must be a bounded safe identifier")
    return normalized


def normalize_approval_actor_id(value: object) -> str:
    """Reject free-form actor metadata before it reaches durable approval state."""
    return _bounded_identifier(value, "decided_by")


def normalize_decision_reason(value: object | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("decision reason must be a bounded stable code")
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > _MAX_REASON_CODE_LENGTH
        or _STABLE_REASON_CODE.fullmatch(normalized) is None
        or normalized not in _APPROVAL_REASON_CODES
    ):
        raise ValueError("decision reason must be a bounded stable code")
    return normalized


def normalize_approval_store_values(values: Mapping[str, Any]) -> None:
    """Apply the public approval metadata boundary to direct durable-store writes."""
    _bounded_identifier(values.get("workflow_run_id"), "workflow_run_id")
    _bounded_identifier(values.get("workflow_step_id"), "workflow_step_id")
    _bounded_identifier(values.get("task_attempt_id"), "task_attempt_id")
    _bounded_identifier(values.get("capability_id"), "capability_id")
    if values.get("payload_hash_algorithm") != CANONICAL_JSON_SHA256_V1:
        raise ValueError("payload hash algorithm is unsupported")
    payload_hash = values.get("payload_hash")
    if not isinstance(payload_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", payload_hash):
        raise ValueError("payload hash must be a SHA-256 digest")


def normalize_approval_decision_status(value: object) -> ApprovalStatus:
    if value not in (ApprovalStatus.APPROVED, ApprovalStatus.DENIED):
        raise ValueError("approval decision must be approved or denied")
    return ApprovalStatus(value)


class ApprovalManager:
    """Creates and validates durable approvals without retaining payload authority."""

    def __init__(
        self,
        uow_factory: Any,
        *,
        clock: Callable[[], datetime],
        fail_after_state_change: bool = False,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._fail_after_state_change = fail_after_state_change

    async def request(
        self,
        *,
        workflow_run_id: str,
        capability_id: str,
        payload: Mapping[str, Any],
        workflow_step_id: str | None = None,
        task_attempt_id: str | None = None,
        expires_at: datetime | None = None,
    ) -> ApprovalRecord:
        workflow_run_id = _bounded_identifier(workflow_run_id, "workflow_run_id")
        capability_id = _bounded_identifier(capability_id, "capability_id")
        if task_attempt_id is None:
            raise ValueError("task_attempt_id is required for exact approval scope")
        task_attempt_id = _bounded_identifier(task_attempt_id, "task_attempt_id")
        if workflow_step_id is not None:
            workflow_step_id = _bounded_identifier(workflow_step_id, "workflow_step_id")
        payload_hash = canonical_payload_hash(payload)
        now = self._clock()
        if expires_at is not None and expires_at <= now:
            raise ValueError("approval expiry must be in the future")

        async with self._uow_factory.transaction() as uow:
            workflow_run = await uow.session.get(WorkflowRunRecord, workflow_run_id)
            if workflow_run is None:
                raise ValueError("approval scope does not match workflow run")
            attempt = await uow.session.get(TaskAttemptRecord, task_attempt_id)
            if attempt is None:
                raise ValueError("approval scope does not match workflow run")
            step = await uow.session.get(WorkflowStepRecord, attempt.workflow_step_id)
            if step is None or step.workflow_run_id != workflow_run_id:
                raise ValueError("approval scope does not match workflow run")
            if workflow_step_id is not None and workflow_step_id != step.id:
                raise ValueError("approval scope does not match workflow run")
            record = await uow.approvals.request(
                workflow_run_id=workflow_run_id,
                workflow_step_id=step.id,
                task_attempt_id=task_attempt_id,
                capability_id=capability_id,
                payload_hash=payload_hash,
                payload_hash_algorithm=CANONICAL_JSON_SHA256_V1,
                expires_at=expires_at,
                requested_at=now,
            )
            await self._append_event(
                uow,
                record,
                event_type="approval.requested",
                actor_type=RuntimeActorType.SYSTEM,
                actor_id=None,
                now=now,
                reason_code="requested",
            )
            await uow.commit()
            return record

    async def decide(
        self,
        approval_id: str,
        *,
        decided_by: str,
        approved: bool,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> bool:
        approval_id = _bounded_identifier(approval_id, "approval_id")
        decided_by = normalize_approval_actor_id(decided_by)
        if not isinstance(approved, bool):
            raise ValueError("approved must be a boolean")
        reason = normalize_decision_reason(reason)
        decided_at = now or self._clock()
        status = ApprovalStatus.APPROVED if approved else ApprovalStatus.DENIED
        async with self._uow_factory.transaction() as uow:
            record = await uow.session.get(ApprovalRecord, approval_id)
            if record is None:
                return False
            decided = await uow.approvals.decide(
                approval_id,
                status=status,
                decided_by=decided_by,
                decision_reason=reason,
                decided_at=decided_at,
            )
            if not decided:
                expired = await uow.approvals.expire_if_due(approval_id, now=decided_at)
                if expired:
                    await self._append_event(
                        uow,
                        record,
                        event_type="approval.expired",
                        actor_type=RuntimeActorType.SYSTEM,
                        actor_id=None,
                        now=decided_at,
                        reason_code="expired",
                    )
                    await uow.commit()
                return False
            if self._fail_after_state_change:
                raise RuntimeError("approval_state_change")
            await self._append_event(
                uow,
                record,
                event_type=("approval.granted" if approved else "approval.denied"),
                actor_type=RuntimeActorType.USER,
                actor_id=decided_by,
                now=decided_at,
                reason_code=reason or ("granted" if approved else "denied"),
            )
            await uow.commit()
            return True

    async def is_valid(
        self,
        approval_id: str,
        *,
        workflow_run_id: str,
        workflow_step_id: str,
        task_attempt_id: str,
        capability_id: str,
        payload: Mapping[str, Any],
        now: datetime | None = None,
    ) -> bool:
        approval_id = _bounded_identifier(approval_id, "approval_id")
        workflow_run_id = _bounded_identifier(workflow_run_id, "workflow_run_id")
        workflow_step_id = _bounded_identifier(workflow_step_id, "workflow_step_id")
        task_attempt_id = _bounded_identifier(task_attempt_id, "task_attempt_id")
        capability_id = _bounded_identifier(capability_id, "capability_id")
        payload_hash = canonical_payload_hash(payload)
        checked_at = now or self._clock()
        async with self._uow_factory.transaction() as uow:
            record = await uow.session.scalar(
                select(ApprovalRecord).where(ApprovalRecord.id == approval_id)
            )
            return bool(
                record is not None
                and record.status == ApprovalStatus.APPROVED
                and record.workflow_run_id == workflow_run_id
                and record.workflow_step_id == workflow_step_id
                and record.task_attempt_id == task_attempt_id
                and record.capability_id == capability_id
                and record.payload_hash_algorithm == CANONICAL_JSON_SHA256_V1
                and record.payload_hash == payload_hash
                and (record.expires_at is None or record.expires_at > checked_at)
            )

    async def invalidate_for_payload_change(
        self,
        task_attempt_id: str,
        payload: Mapping[str, Any],
        *,
        now: datetime | None = None,
    ) -> int:
        task_attempt_id = _bounded_identifier(task_attempt_id, "task_attempt_id")
        changed_at = now or self._clock()
        payload_hash = canonical_payload_hash(payload)
        async with self._uow_factory.transaction() as uow:
            records = list(
                (
                    await uow.session.scalars(
                        select(ApprovalRecord).where(
                            ApprovalRecord.task_attempt_id == task_attempt_id,
                            ApprovalRecord.status.in_(
                                (ApprovalStatus.PENDING, ApprovalStatus.APPROVED)
                            ),
                            ApprovalRecord.payload_hash != payload_hash,
                        )
                    )
                ).all()
            )
            invalidated = await uow.approvals.invalidate_for_payload_change(
                task_attempt_id,
                current_payload_hash=payload_hash,
                now=changed_at,
            )
            if invalidated:
                for record in records:
                    await self._append_event(
                        uow,
                        record,
                        event_type="approval.invalidated",
                        actor_type=RuntimeActorType.SYSTEM,
                        actor_id=None,
                        now=changed_at,
                        reason_code="payload_changed",
                    )
                await uow.commit()
            return invalidated

    async def _append_event(
        self,
        uow: Any,
        record: ApprovalRecord,
        *,
        event_type: str,
        actor_type: RuntimeActorType,
        actor_id: str | None,
        now: datetime,
        reason_code: str,
    ) -> None:
        await uow.events.append(
            event_type=event_type,
            event_version=1,
            aggregate_type="approval",
            aggregate_id=record.id,
            workflow_run_id=record.workflow_run_id,
            workflow_step_id=record.workflow_step_id,
            task_attempt_id=record.task_attempt_id,
            actor_type=actor_type,
            actor_id=actor_id,
            occurred_at=now,
            payload_json={
                "status": event_type.rsplit(".", 1)[-1],
                "reason_code": reason_code,
                "capability_id": record.capability_id,
                "payload_hash": record.payload_hash,
            },
            metadata_json={"event_version": 1},
            sensitivity="metadata",
        )
