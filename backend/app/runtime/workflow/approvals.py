"""Payload-bound approval operations backed by the runtime unit of work."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import select

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


def canonical_payload_hash(
    payload: Mapping[str, Any],
    algorithm: str = CANONICAL_JSON_SHA256_V1,
) -> str:
    """Hash the exact UTF-8 canonical JSON representation of a safe payload."""
    if algorithm != CANONICAL_JSON_SHA256_V1:
        raise ValueError("unsupported payload hash algorithm")
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be a JSON object")
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


def _decision_reason(value: object | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("decision reason must be a bounded safe string")
    normalized = value.strip()
    if not normalized or len(normalized) > 256 or any(
        character in normalized for character in "\r\n\x00"
    ):
        raise ValueError("decision reason must be a bounded safe string")
    return normalized


class ApprovalManager:
    """Creates and validates durable approvals without retaining payload authority."""

    def __init__(self, uow_factory: Any, *, clock: Callable[[], datetime]) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

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
        if workflow_step_id is not None:
            workflow_step_id = _bounded_identifier(workflow_step_id, "workflow_step_id")
        if task_attempt_id is not None:
            task_attempt_id = _bounded_identifier(task_attempt_id, "task_attempt_id")
        payload_hash = canonical_payload_hash(payload)
        now = self._clock()
        if expires_at is not None and expires_at <= now:
            raise ValueError("approval expiry must be in the future")

        async with self._uow_factory.transaction() as uow:
            workflow_run = await uow.session.get(WorkflowRunRecord, workflow_run_id)
            if workflow_run is None:
                raise ValueError("approval scope does not match workflow run")
            step: WorkflowStepRecord | None = None
            if workflow_step_id is not None:
                step = await uow.session.get(WorkflowStepRecord, workflow_step_id)
                if step is None or step.workflow_run_id != workflow_run_id:
                    raise ValueError("approval scope does not match workflow run")
            if task_attempt_id is not None:
                attempt = await uow.session.get(TaskAttemptRecord, task_attempt_id)
                if attempt is None:
                    raise ValueError("approval scope does not match workflow run")
                attempt_step = await uow.session.get(
                    WorkflowStepRecord, attempt.workflow_step_id
                )
                if (
                    attempt_step is None
                    or attempt_step.workflow_run_id != workflow_run_id
                    or (step is not None and step.id != attempt_step.id)
                ):
                    raise ValueError("approval scope does not match workflow run")
            record = await uow.approvals.request(
                workflow_run_id=workflow_run_id,
                workflow_step_id=workflow_step_id,
                task_attempt_id=task_attempt_id,
                capability_id=capability_id,
                payload_hash=payload_hash,
                payload_hash_algorithm=CANONICAL_JSON_SHA256_V1,
                expires_at=expires_at,
                requested_at=now,
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
        decided_by = _bounded_identifier(decided_by, "decided_by")
        if not isinstance(approved, bool):
            raise ValueError("approved must be a boolean")
        reason = _decision_reason(reason)
        decided_at = now or self._clock()
        status = ApprovalStatus.APPROVED if approved else ApprovalStatus.DENIED
        async with self._uow_factory.transaction() as uow:
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
                    await uow.commit()
                return False
            await uow.commit()
            return True

    async def is_valid(
        self,
        approval_id: str,
        *,
        capability_id: str,
        payload: Mapping[str, Any],
        now: datetime | None = None,
    ) -> bool:
        approval_id = _bounded_identifier(approval_id, "approval_id")
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
            invalidated = await uow.approvals.invalidate_for_payload_change(
                task_attempt_id,
                current_payload_hash=payload_hash,
                now=changed_at,
            )
            if invalidated:
                await uow.commit()
            return invalidated
