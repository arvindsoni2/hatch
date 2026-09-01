"""Short transactional persistence operations for durable workflow ownership."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
import logging
import re

from sqlalchemy import and_, exists, or_, select, update

from ..evaluation.models import ExecutionRole
from ..events.repository import enforce_metadata_only
from ..storage.contracts import RuntimeUnitOfWorkFactory
from .claims import require_worker_id
from .models import (
    ExecutionClaimRecord,
    ExecutionClaimPurpose,
    ExecutionClaimStatus,
    TaskAttemptRecord,
    TaskAttemptStatus,
    WaitingReason,
    WorkflowRunRecord,
    WorkflowRunStatus,
    WorkflowStepRecord,
    WorkflowStepStatus,
)
from .retry import normalize_failure_code, normalize_retry_metadata


_RECONCILIATION_CODE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_IDEMPOTENCY_CLASSES = {
    "idempotent",
    "idempotent_with_key",
    "check_before_retry",
    "non_retryable_side_effect",
}
_SIDE_EFFECT_CLASSES = {
    "pure",
    "read_only_external",
    "prepare_side_effect",
    "commit_side_effect",
    "artifact_generation",
}
_AMBIGUOUS_SIDE_EFFECT_CLASSES = {
    "prepare_side_effect",
    "commit_side_effect",
    "artifact_generation",
}
_AMBIGUOUS_IDEMPOTENCY_CLASSES = {
    "check_before_retry",
    "non_retryable_side_effect",
}
_DEFAULT_RECOVERY_BATCH_SIZE = 25
_MAX_RECOVERY_BATCH_SIZE = 100
_DEFAULT_RECOVERY_BACKOFF_SECONDS = 1
_MAX_RECOVERY_BACKOFF_SECONDS = 3600
_RECOVERY_ERROR_CODE = "recovery_failed"

logger = logging.getLogger(__name__)


def _requires_reconciliation(
    side_effect_class: str | None,
    idempotency_class: str | None,
) -> bool:
    return (
        side_effect_class in _AMBIGUOUS_SIDE_EFFECT_CLASSES
        or idempotency_class in _AMBIGUOUS_IDEMPOTENCY_CLASSES
    )


def validate_recovery_batch_size(batch_size: object) -> int:
    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or not 1 <= batch_size <= _MAX_RECOVERY_BATCH_SIZE
    ):
        raise ValueError(
            f"batch_size must be an integer from 1 to {_MAX_RECOVERY_BATCH_SIZE}"
        )
    return batch_size


def validate_recovery_backoff_seconds(backoff_seconds: object) -> int:
    """Accept a small, bounded retry delay for individual recovery failures."""
    if (
        isinstance(backoff_seconds, bool)
        or not isinstance(backoff_seconds, int)
        or not 1 <= backoff_seconds <= _MAX_RECOVERY_BACKOFF_SECONDS
    ):
        raise ValueError(
            "recovery_backoff_seconds must be an integer from 1 to "
            f"{_MAX_RECOVERY_BACKOFF_SECONDS}"
        )
    return backoff_seconds


def normalize_reconciliation_binding(
    capability_id: object,
    capability_version: object,
    idempotency_class: object,
    reconciliation_reference: object,
) -> tuple[str, int, str, str]:
    """Accept only bounded metadata-safe durable ambiguity descriptors."""
    values = {
        "capability_id": capability_id,
        "idempotency_class": idempotency_class,
        "reconciliation_reference": reconciliation_reference,
    }
    normalized: dict[str, str] = {}
    for field, value in values.items():
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a bounded stable code")
        item = value.strip()
        if not item or len(item) > 128 or _RECONCILIATION_CODE.fullmatch(item) is None:
            raise ValueError(f"{field} must be a bounded stable code")
        normalized[field] = item
    if normalized["idempotency_class"] not in _IDEMPOTENCY_CLASSES:
        raise ValueError("idempotency_class must be a supported stable code")
    if (
        isinstance(capability_version, bool)
        or not isinstance(capability_version, int)
        or capability_version < 1
    ):
        raise ValueError("capability_version must be positive")
    return (
        normalized["capability_id"],
        capability_version,
        normalized["idempotency_class"],
        normalized["reconciliation_reference"],
    )


def normalize_execution_intent_binding(
    capability_id: object,
    capability_version: object,
    side_effect_class: object,
    idempotency_class: object,
    reconciliation_reference: object,
) -> tuple[str, int, str, str, str]:
    """Accept the complete bounded descriptor binding for external work."""
    capability_id, capability_version, idempotency_class, reference = (
        normalize_reconciliation_binding(
            capability_id,
            capability_version,
            idempotency_class,
            reconciliation_reference,
        )
    )
    if not isinstance(side_effect_class, str):
        raise ValueError("side_effect_class must be a supported stable code")
    normalized_side_effect = side_effect_class.strip()
    if normalized_side_effect not in _SIDE_EFFECT_CLASSES:
        raise ValueError("side_effect_class must be a supported stable code")
    return (
        capability_id,
        capability_version,
        normalized_side_effect,
        idempotency_class,
        reference,
    )


class SQLiteWorkflowRepository:
    """Durable workflow operations, each enclosed in a small database transaction."""

    def __init__(self, uow_factory: RuntimeUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    @staticmethod
    def _active_claim(claim: ExecutionClaimRecord, now: datetime) -> object:
        """A durable, unexpired ownership predicate; caller objects are untrusted."""
        return exists().where(
            ExecutionClaimRecord.id == claim.id,
            ExecutionClaimRecord.task_attempt_id == claim.task_attempt_id,
            ExecutionClaimRecord.fencing_token == claim.fencing_token,
            ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
            ExecutionClaimRecord.lease_expires_at > now,
        )

    async def _sync_lifecycle(
        self, uow: object, workflow_step_id: str, now: datetime
    ) -> None:
        """Derive step/run aggregates from durable child state in the same UoW.

        R2 creates one step per run, but deriving from all attempts and all steps
        keeps the persistence rule safe when a later release introduces siblings.
        """
        session = uow.session  # type: ignore[attr-defined]
        step = await session.get(WorkflowStepRecord, workflow_step_id)
        if step is None:
            raise RuntimeError("workflow step disappeared during lifecycle update")
        attempts = list(
            (
                await session.scalars(
                    select(TaskAttemptRecord)
                    .where(TaskAttemptRecord.workflow_step_id == workflow_step_id)
                    .order_by(TaskAttemptRecord.attempt_number)
                )
            ).all()
        )
        statuses = {attempt.status for attempt in attempts}
        latest = attempts[-1] if attempts else None
        if TaskAttemptStatus.RUNNING in statuses:
            step_status = WorkflowStepStatus.RUNNING
        elif statuses & {TaskAttemptStatus.WAITING, TaskAttemptStatus.OUTCOME_UNKNOWN}:
            step_status = WorkflowStepStatus.WAITING
        elif TaskAttemptStatus.PENDING in statuses:
            step_status = WorkflowStepStatus.PENDING
        elif TaskAttemptStatus.SUCCEEDED in statuses:
            step_status = WorkflowStepStatus.COMPLETED
        elif attempts and statuses <= {
            TaskAttemptStatus.FAILED,
            TaskAttemptStatus.CANCELLED,
        }:
            step_status = WorkflowStepStatus.FAILED
        else:
            step_status = WorkflowStepStatus.PENDING
        await session.execute(
            update(WorkflowStepRecord)
            .where(WorkflowStepRecord.id == workflow_step_id)
            .values(
                status=step_status,
                waiting_reason=(
                    latest.waiting_reason
                    if step_status == WorkflowStepStatus.WAITING and latest is not None
                    else None
                ),
                completed_at=(
                    now
                    if step_status
                    in (WorkflowStepStatus.COMPLETED, WorkflowStepStatus.FAILED)
                    else None
                ),
                failure_code=(
                    latest.failure_code
                    if step_status == WorkflowStepStatus.FAILED and latest is not None
                    else None
                ),
                updated_at=now,
            )
        )
        steps = list(
            (
                await session.scalars(
                    select(WorkflowStepRecord)
                    .where(WorkflowStepRecord.workflow_run_id == step.workflow_run_id)
                    .order_by(WorkflowStepRecord.step_order)
                )
            ).all()
        )
        step_statuses = {item.status for item in steps}
        if WorkflowStepStatus.RUNNING in step_statuses:
            run_status = WorkflowRunStatus.RUNNING
        elif WorkflowStepStatus.WAITING in step_statuses:
            run_status = WorkflowRunStatus.WAITING
        elif WorkflowStepStatus.PENDING in step_statuses:
            run_status = WorkflowRunStatus.PENDING
        elif steps and step_statuses == {WorkflowStepStatus.COMPLETED}:
            run_status = WorkflowRunStatus.COMPLETED
        elif steps and step_statuses <= {
            WorkflowStepStatus.FAILED,
            WorkflowStepStatus.CANCELLED,
        }:
            run_status = WorkflowRunStatus.FAILED
        else:
            run_status = WorkflowRunStatus.PENDING
        result_ref = None
        if run_status == WorkflowRunStatus.COMPLETED:
            succeeded = next(
                (
                    attempt
                    for attempt in reversed(attempts)
                    if attempt.status == TaskAttemptStatus.SUCCEEDED
                ),
                None,
            )
            result_ref = succeeded.result_ref_json if succeeded is not None else None
        failure_code = None
        if run_status == WorkflowRunStatus.FAILED:
            failed_step = next(
                (
                    item
                    for item in reversed(steps)
                    if item.status == WorkflowStepStatus.FAILED
                ),
                None,
            )
            failure_code = failed_step.failure_code if failed_step is not None else None
        await session.execute(
            update(WorkflowRunRecord)
            .where(WorkflowRunRecord.id == step.workflow_run_id)
            .values(
                status=run_status,
                completed_at=(
                    now
                    if run_status
                    in (WorkflowRunStatus.COMPLETED, WorkflowRunStatus.FAILED)
                    else None
                ),
                result_ref_json=result_ref,
                failure_code=failure_code,
                updated_at=now,
            )
        )

    async def create_run(
        self,
        *,
        workflow_definition_id: str,
        workflow_definition_version: int,
        input_ref: dict[str, object],
        domain_ref: dict[str, object],
        mode: str,
        max_attempts: int,
    ) -> WorkflowRunRecord:
        domain_type = str(domain_ref.get("domain_type") or "runtime")
        domain_id = domain_ref.get("domain_id")
        if domain_id is not None:
            domain_id = str(domain_id)
        async with self._uow_factory.transaction() as uow:
            run = await uow.workflows.create_run(
                workflow_definition_id=workflow_definition_id,
                workflow_definition_version=workflow_definition_version,
                domain_type=domain_type,
                domain_id=domain_id,
                runtime_mode=mode,
                max_attempts=max_attempts,
                input_ref_json=input_ref,
            )
            step = await uow.workflows.create_step(
                workflow_run_id=run.id,
                step_key="execute",
                step_order=1,
                task_id=workflow_definition_id,
                task_version=workflow_definition_version,
            )
            await uow.workflows.create_attempt(
                workflow_step_id=step.id, attempt_number=1
            )
            await uow.commit()
            return run

    async def get_attempt(self, attempt_id: str) -> TaskAttemptRecord | None:
        """Read one durable attempt through the repository boundary."""
        async with self._uow_factory.transaction() as uow:
            return await uow.workflows.get_attempt(attempt_id)

    async def transition_waiting(
        self,
        claim: ExecutionClaimRecord,
        *,
        reason: WaitingReason,
        now: datetime,
    ) -> bool:
        """Release only the current fenced owner into a durable wait state."""
        active_claim = self._active_claim(claim, now)
        async with self._uow_factory.transaction() as uow:
            transitioned = await uow.session.execute(
                update(TaskAttemptRecord)
                .where(
                    TaskAttemptRecord.id == claim.task_attempt_id,
                    TaskAttemptRecord.status == TaskAttemptStatus.RUNNING,
                    TaskAttemptRecord.current_claim_id == claim.id,
                    TaskAttemptRecord.claim_fencing_token == claim.fencing_token,
                    active_claim,
                )
                .values(
                    status=TaskAttemptStatus.WAITING,
                    waiting_reason=reason,
                    current_claim_id=None,
                    updated_at=now,
                )
            )
            if transitioned.rowcount != 1:
                return False
            released = await uow.session.execute(
                update(ExecutionClaimRecord)
                .where(
                    ExecutionClaimRecord.id == claim.id,
                    ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
                )
                .values(status=ExecutionClaimStatus.RELEASED, released_at=now)
            )
            if released.rowcount != 1:
                raise RuntimeError("claim ownership changed during waiting transition")
            attempt = await uow.session.get(TaskAttemptRecord, claim.task_attempt_id)
            if attempt is None:
                raise RuntimeError("waiting attempt disappeared before commit")
            await self._sync_lifecycle(uow, attempt.workflow_step_id, now)
            await uow.commit()
            return True

    async def resume_waiting(
        self, attempt_id: str, *, now: datetime
    ) -> TaskAttemptRecord | None:
        """Make a human-blocked attempt claimable without reviving an old claim."""
        async with self._uow_factory.transaction() as uow:
            resumed = await uow.session.execute(
                update(TaskAttemptRecord)
                .where(
                    TaskAttemptRecord.id == attempt_id,
                    TaskAttemptRecord.status == TaskAttemptStatus.WAITING,
                    TaskAttemptRecord.waiting_reason.in_(
                        (WaitingReason.APPROVAL, WaitingReason.USER_INPUT)
                    ),
                    TaskAttemptRecord.current_claim_id.is_(None),
                )
                .values(
                    status=TaskAttemptStatus.PENDING,
                    waiting_reason=None,
                    updated_at=now,
                )
            )
            if resumed.rowcount != 1:
                return None
            attempt = await uow.session.get(TaskAttemptRecord, attempt_id)
            if attempt is None:
                raise RuntimeError("resumed attempt disappeared before commit")
            await self._sync_lifecycle(uow, attempt.workflow_step_id, now)
            await uow.commit()
            return attempt

    async def _claim_pending(
        self, worker_id: str, now: datetime, lease_duration: timedelta
    ) -> ExecutionClaimRecord | None:
        async with self._uow_factory.transaction() as uow:
            promoted_step_ids = set(
                (
                    await uow.session.scalars(
                        select(TaskAttemptRecord.workflow_step_id).where(
                            TaskAttemptRecord.status == TaskAttemptStatus.WAITING,
                            TaskAttemptRecord.waiting_reason
                            == WaitingReason.RETRY_TIME,
                            TaskAttemptRecord.not_before <= now,
                        )
                    )
                ).all()
            )
            await uow.session.execute(
                update(TaskAttemptRecord)
                .where(
                    TaskAttemptRecord.status == TaskAttemptStatus.WAITING,
                    TaskAttemptRecord.waiting_reason == WaitingReason.RETRY_TIME,
                    TaskAttemptRecord.not_before <= now,
                )
                .values(
                    status=TaskAttemptStatus.PENDING,
                    waiting_reason=None,
                    updated_at=now,
                )
            )
            candidate = await uow.session.scalar(
                select(TaskAttemptRecord)
                .where(
                    TaskAttemptRecord.status == TaskAttemptStatus.PENDING,
                    (TaskAttemptRecord.not_before.is_(None))
                    | (TaskAttemptRecord.not_before <= now),
                )
                .order_by(TaskAttemptRecord.created_at, TaskAttemptRecord.id)
                .limit(1)
            )
            if candidate is None:
                for workflow_step_id in promoted_step_ids:
                    await self._sync_lifecycle(uow, workflow_step_id, now)
                if promoted_step_ids:
                    await uow.commit()
                return None
            claim_id = str(uuid.uuid4())
            lease_expires_at = now + lease_duration
            token = await uow.session.scalar(
                update(TaskAttemptRecord)
                .where(
                    TaskAttemptRecord.id == candidate.id,
                    TaskAttemptRecord.status == TaskAttemptStatus.PENDING,
                    TaskAttemptRecord.claim_fencing_token
                    == candidate.claim_fencing_token,
                    (TaskAttemptRecord.not_before.is_(None))
                    | (TaskAttemptRecord.not_before <= now),
                )
                .values(
                    status=TaskAttemptStatus.RUNNING,
                    claim_fencing_token=TaskAttemptRecord.claim_fencing_token + 1,
                    current_claim_id=claim_id,
                    started_at=now,
                    updated_at=now,
                )
                .returning(TaskAttemptRecord.claim_fencing_token)
            )
            if token is None:
                return None
            await uow.session.execute(
                update(ExecutionClaimRecord)
                .where(
                    ExecutionClaimRecord.task_attempt_id == candidate.id,
                    ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
                )
                .values(status=ExecutionClaimStatus.SUPERSEDED, released_at=now)
            )
            claim = ExecutionClaimRecord(
                id=claim_id,
                task_attempt_id=candidate.id,
                fencing_token=token,
                claimed_by=worker_id,
                purpose=ExecutionClaimPurpose.EXECUTION,
                claimed_at=now,
                lease_expires_at=lease_expires_at,
                status=ExecutionClaimStatus.ACTIVE,
            )
            uow.session.add(claim)
            await uow.session.flush()
            promoted_step_ids.add(candidate.workflow_step_id)
            for workflow_step_id in promoted_step_ids:
                await self._sync_lifecycle(uow, workflow_step_id, now)
            await uow.commit()
            return claim

    async def claim_next(
        self, worker_id: str, now: datetime, lease_duration: timedelta
    ) -> ExecutionClaimRecord | None:
        return await self._claim_pending(
            require_worker_id(worker_id), now, lease_duration
        )

    async def reclaim(
        self,
        attempt_id: str,
        worker_id: str,
        now: datetime,
        lease_duration: timedelta,
    ) -> ExecutionClaimRecord | None:
        """Replace an expired owner with a strictly newer fencing token."""
        worker_id = require_worker_id(worker_id)
        async with self._uow_factory.transaction() as uow:
            previous = await uow.session.scalar(
                select(ExecutionClaimRecord).where(
                    ExecutionClaimRecord.task_attempt_id == attempt_id,
                    ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
                    ExecutionClaimRecord.lease_expires_at <= now,
                    (ExecutionClaimRecord.recovery_not_before.is_(None))
                    | (ExecutionClaimRecord.recovery_not_before <= now),
                )
            )
            if previous is None:
                return None
            attempt = await uow.session.get(TaskAttemptRecord, attempt_id)
            if attempt is None or (
                attempt.execution_intent_active
                and _requires_reconciliation(
                    attempt.side_effect_class,
                    attempt.idempotency_class,
                )
            ):
                return None
            still_reclaimable = exists().where(
                ExecutionClaimRecord.id == previous.id,
                ExecutionClaimRecord.task_attempt_id == attempt_id,
                ExecutionClaimRecord.fencing_token == previous.fencing_token,
                ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
                ExecutionClaimRecord.lease_expires_at <= now,
                (ExecutionClaimRecord.recovery_not_before.is_(None))
                | (ExecutionClaimRecord.recovery_not_before <= now),
            )
            claim_id = str(uuid.uuid4())
            lease_expires_at = now + lease_duration
            token = await uow.session.scalar(
                update(TaskAttemptRecord)
                .where(
                    TaskAttemptRecord.id == attempt_id,
                    TaskAttemptRecord.status == TaskAttemptStatus.RUNNING,
                    TaskAttemptRecord.current_claim_id == previous.id,
                    TaskAttemptRecord.claim_fencing_token == previous.fencing_token,
                    or_(
                        TaskAttemptRecord.execution_intent_active.is_(False),
                        and_(
                            TaskAttemptRecord.execution_intent_active.is_(True),
                            TaskAttemptRecord.side_effect_class.not_in(
                                _AMBIGUOUS_SIDE_EFFECT_CLASSES
                            ),
                            TaskAttemptRecord.idempotency_class.not_in(
                                _AMBIGUOUS_IDEMPOTENCY_CLASSES
                            ),
                        ),
                    ),
                    still_reclaimable,
                )
                .values(
                    current_claim_id=claim_id,
                    claim_fencing_token=TaskAttemptRecord.claim_fencing_token + 1,
                    execution_intent_active=False,
                    updated_at=now,
                )
                .returning(TaskAttemptRecord.claim_fencing_token)
            )
            if token is None:
                return None
            await uow.session.execute(
                update(ExecutionClaimRecord)
                .where(
                    ExecutionClaimRecord.id == previous.id,
                    ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
                    ExecutionClaimRecord.lease_expires_at <= now,
                    (ExecutionClaimRecord.recovery_not_before.is_(None))
                    | (ExecutionClaimRecord.recovery_not_before <= now),
                )
                .values(status=ExecutionClaimStatus.SUPERSEDED, released_at=now)
            )
            claim = ExecutionClaimRecord(
                id=claim_id,
                task_attempt_id=attempt_id,
                fencing_token=token,
                claimed_by=worker_id,
                purpose=ExecutionClaimPurpose.EXECUTION,
                claimed_at=now,
                lease_expires_at=lease_expires_at,
                status=ExecutionClaimStatus.ACTIVE,
            )
            uow.session.add(claim)
            await uow.session.flush()
            current_attempt = await uow.session.get(TaskAttemptRecord, attempt_id)
            if current_attempt is None:
                raise RuntimeError("reclaimed attempt disappeared before commit")
            await self._sync_lifecycle(uow, current_attempt.workflow_step_id, now)
            await uow.commit()
            return claim

    async def renew_claim(
        self,
        claim: ExecutionClaimRecord,
        now: datetime,
        lease_duration: timedelta,
    ) -> bool:
        """Extend a lease only while the claim is still current durable owner."""
        current_attempt = exists().where(
            TaskAttemptRecord.id == claim.task_attempt_id,
            TaskAttemptRecord.status.in_(
                (TaskAttemptStatus.RUNNING, TaskAttemptStatus.OUTCOME_UNKNOWN)
            ),
            TaskAttemptRecord.current_claim_id == claim.id,
            TaskAttemptRecord.claim_fencing_token == claim.fencing_token,
        )
        async with self._uow_factory.transaction() as uow:
            result = await uow.session.execute(
                update(ExecutionClaimRecord)
                .where(
                    ExecutionClaimRecord.id == claim.id,
                    ExecutionClaimRecord.task_attempt_id == claim.task_attempt_id,
                    ExecutionClaimRecord.fencing_token == claim.fencing_token,
                    ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
                    ExecutionClaimRecord.lease_expires_at > now,
                    current_attempt,
                )
                .values(lease_expires_at=now + lease_duration)
            )
            if result.rowcount != 1:
                return False
            await uow.commit()
            return True

    async def finalize(
        self,
        claim: ExecutionClaimRecord,
        result_ref: dict[str, object],
        now: datetime,
    ) -> bool:
        """Persist a result only when the supplied claim remains the owner."""
        active_claim = self._active_claim(claim, now)
        async with self._uow_factory.transaction() as uow:
            finalized = await uow.session.execute(
                update(TaskAttemptRecord)
                .where(
                    TaskAttemptRecord.id == claim.task_attempt_id,
                    TaskAttemptRecord.status.in_(
                        (TaskAttemptStatus.RUNNING, TaskAttemptStatus.OUTCOME_UNKNOWN)
                    ),
                    TaskAttemptRecord.current_claim_id == claim.id,
                    TaskAttemptRecord.claim_fencing_token == claim.fencing_token,
                    active_claim,
                )
                .values(
                    status=TaskAttemptStatus.SUCCEEDED,
                    result_ref_json=result_ref,
                    current_claim_id=None,
                    execution_intent_active=False,
                    finished_at=now,
                    updated_at=now,
                )
            )
            if finalized.rowcount != 1:
                return False
            released = await uow.session.execute(
                update(ExecutionClaimRecord)
                .where(
                    ExecutionClaimRecord.id == claim.id,
                    ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
                )
                .values(status=ExecutionClaimStatus.RELEASED, released_at=now)
            )
            if released.rowcount != 1:
                raise RuntimeError("claim ownership changed during finalization")
            attempt = await uow.session.get(TaskAttemptRecord, claim.task_attempt_id)
            if attempt is None:
                raise RuntimeError("finalized attempt disappeared before commit")
            await self._sync_lifecycle(uow, attempt.workflow_step_id, now)
            await uow.commit()
            return True

    async def begin_execution_intent(
        self,
        claim: ExecutionClaimRecord,
        *,
        now: datetime,
        capability_id: str,
        capability_version: int,
        side_effect_class: str,
        idempotency_class: str,
        reconciliation_reference: str,
    ) -> bool:
        """Commit a fenced, privacy-safe binding before adapter work begins."""
        (
            capability_id,
            capability_version,
            side_effect_class,
            idempotency_class,
            reconciliation_reference,
        ) = normalize_execution_intent_binding(
            capability_id,
            capability_version,
            side_effect_class,
            idempotency_class,
            reconciliation_reference,
        )
        active_claim = self._active_claim(claim, now)
        async with self._uow_factory.transaction() as uow:
            bound = await uow.session.execute(
                update(TaskAttemptRecord)
                .where(
                    TaskAttemptRecord.id == claim.task_attempt_id,
                    TaskAttemptRecord.status == TaskAttemptStatus.RUNNING,
                    TaskAttemptRecord.current_claim_id == claim.id,
                    TaskAttemptRecord.claim_fencing_token == claim.fencing_token,
                    TaskAttemptRecord.execution_intent_active.is_(False),
                    active_claim,
                )
                .values(
                    capability_id=capability_id,
                    capability_version=capability_version,
                    side_effect_class=side_effect_class,
                    idempotency_class=idempotency_class,
                    reconciliation_reference=reconciliation_reference,
                    execution_intent_active=True,
                    updated_at=now,
                )
            )
            if bound.rowcount != 1:
                return False
            await uow.commit()
            return True

    async def persist_execution_result(
        self,
        claim: ExecutionClaimRecord,
        *,
        execution_role: str,
        capability_id: str,
        capability_version: int,
        side_effect_class: str,
        idempotency_class: str,
        reconciliation_reference: str,
        result_class: str,
        started_at: datetime,
        finished_at: datetime,
        latency_ms: int,
        metadata: dict[str, object],
        outcome_unknown: dict[str, object] | None,
    ) -> bool:
        """Insert one execution result only while the supplied fence still owns it."""
        try:
            role = ExecutionRole(execution_role)
        except ValueError as error:
            raise ValueError("execution_role is unsupported") from error
        if not isinstance(result_class, str) or not result_class:
            raise ValueError("result_class is required")
        if finished_at < started_at or started_at < claim.claimed_at:
            raise ValueError("execution timestamps are outside the claim lifetime")
        if (
            isinstance(latency_ms, bool)
            or not isinstance(latency_ms, int)
            or latency_ms < 0
        ):
            raise ValueError("latency_ms must be a non-negative integer")
        enforce_metadata_only(metadata, path="execution.metadata")
        attempt_binding = normalize_execution_intent_binding(
            capability_id,
            capability_version,
            side_effect_class,
            idempotency_class,
            reconciliation_reference,
        )
        if outcome_unknown is not None and (
            outcome_unknown.get("idempotency_class") != attempt_binding[3]
            or outcome_unknown.get("reconciliation_reference") != attempt_binding[4]
        ):
            raise ValueError("outcome_unknown must match execution intent binding")
        retain_execution_disposition = _requires_reconciliation(
            attempt_binding[2],
            attempt_binding[3],
        )

        current_attempt = exists().where(
            TaskAttemptRecord.id == claim.task_attempt_id,
            TaskAttemptRecord.status == TaskAttemptStatus.RUNNING,
            TaskAttemptRecord.current_claim_id == claim.id,
            TaskAttemptRecord.claim_fencing_token == claim.fencing_token,
            TaskAttemptRecord.capability_id == attempt_binding[0],
            TaskAttemptRecord.capability_version == attempt_binding[1],
            TaskAttemptRecord.side_effect_class == attempt_binding[2],
            TaskAttemptRecord.idempotency_class == attempt_binding[3],
            TaskAttemptRecord.reconciliation_reference == attempt_binding[4],
            TaskAttemptRecord.execution_intent_active.is_(True),
        )
        active_claim = self._active_claim(claim, finished_at)
        async with self._uow_factory.transaction() as uow:
            # The no-op conditional update acquires the database write lock while
            # atomically validating claim/attempt ownership. A concurrent reclaim
            # cannot pass between this fence check and the execution insert.
            owned = await uow.session.execute(
                update(ExecutionClaimRecord)
                .where(
                    ExecutionClaimRecord.id == claim.id,
                    ExecutionClaimRecord.task_attempt_id == claim.task_attempt_id,
                    ExecutionClaimRecord.fencing_token == claim.fencing_token,
                    ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
                    ExecutionClaimRecord.lease_expires_at > finished_at,
                    current_attempt,
                    active_claim,
                )
                .values(status=ExecutionClaimRecord.status)
            )
            if owned.rowcount != 1:
                return False
            await uow.evaluations.record_execution(
                task_attempt_id=claim.task_attempt_id,
                execution_role=role,
                capability_id=capability_id,
                capability_version=capability_version,
                started_at=started_at,
                finished_at=finished_at,
                result_class=result_class,
                latency_ms=latency_ms,
                metadata_json=metadata,
            )
            if outcome_unknown is not None:
                marked = await uow.session.execute(
                    update(TaskAttemptRecord)
                    .where(
                        TaskAttemptRecord.id == claim.task_attempt_id,
                        TaskAttemptRecord.status == TaskAttemptStatus.RUNNING,
                        TaskAttemptRecord.current_claim_id == claim.id,
                        TaskAttemptRecord.claim_fencing_token == claim.fencing_token,
                        TaskAttemptRecord.execution_intent_active.is_(True),
                    )
                    .values(
                        status=TaskAttemptStatus.OUTCOME_UNKNOWN,
                        current_claim_id=None,
                        execution_intent_active=False,
                        updated_at=finished_at,
                    )
                )
                if marked.rowcount != 1:
                    raise RuntimeError(
                        "claim ownership changed during execution persistence"
                    )
                released = await uow.session.execute(
                    update(ExecutionClaimRecord)
                    .where(
                        ExecutionClaimRecord.id == claim.id,
                        ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
                    )
                    .values(
                        status=ExecutionClaimStatus.RELEASED,
                        released_at=finished_at,
                    )
                )
                if released.rowcount != 1:
                    raise RuntimeError(
                        "claim ownership changed during outcome persistence"
                    )
                attempt = await uow.session.get(
                    TaskAttemptRecord, claim.task_attempt_id
                )
                if attempt is None:
                    raise RuntimeError("execution attempt disappeared before commit")
                await self._sync_lifecycle(uow, attempt.workflow_step_id, finished_at)
            else:
                closed = await uow.session.execute(
                    update(TaskAttemptRecord)
                    .where(
                        TaskAttemptRecord.id == claim.task_attempt_id,
                        TaskAttemptRecord.status == TaskAttemptStatus.RUNNING,
                        TaskAttemptRecord.current_claim_id == claim.id,
                        TaskAttemptRecord.claim_fencing_token == claim.fencing_token,
                        TaskAttemptRecord.execution_intent_active.is_(True),
                    )
                    .values(
                        execution_intent_active=retain_execution_disposition,
                        updated_at=finished_at,
                    )
                )
                if closed.rowcount != 1:
                    raise RuntimeError(
                        "claim ownership changed during execution persistence"
                    )
            await uow.commit()
            return True

    async def mark_outcome_unknown(
        self,
        claim: ExecutionClaimRecord,
        *,
        now: datetime,
        capability_id: str,
        capability_version: int,
        idempotency_class: str,
        reconciliation_reference: str,
    ) -> bool:
        """Durably stop execution before an ambiguous external outcome is checked."""
        (
            capability_id,
            capability_version,
            idempotency_class,
            reconciliation_reference,
        ) = normalize_reconciliation_binding(
            capability_id,
            capability_version,
            idempotency_class,
            reconciliation_reference,
        )
        active_claim = self._active_claim(claim, now)
        async with self._uow_factory.transaction() as uow:
            marked = await uow.session.execute(
                update(TaskAttemptRecord)
                .where(
                    TaskAttemptRecord.id == claim.task_attempt_id,
                    TaskAttemptRecord.status == TaskAttemptStatus.RUNNING,
                    TaskAttemptRecord.current_claim_id == claim.id,
                    TaskAttemptRecord.claim_fencing_token == claim.fencing_token,
                    active_claim,
                )
                .values(
                    status=TaskAttemptStatus.OUTCOME_UNKNOWN,
                    current_claim_id=None,
                    capability_id=capability_id,
                    capability_version=capability_version,
                    idempotency_class=idempotency_class,
                    reconciliation_reference=reconciliation_reference,
                    execution_intent_active=False,
                    updated_at=now,
                )
            )
            if marked.rowcount != 1:
                return False
            released = await uow.session.execute(
                update(ExecutionClaimRecord)
                .where(
                    ExecutionClaimRecord.id == claim.id,
                    ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
                )
                .values(status=ExecutionClaimStatus.RELEASED, released_at=now)
            )
            if released.rowcount != 1:
                raise RuntimeError(
                    "claim ownership changed during unknown-outcome transition"
                )
            attempt = await uow.session.get(TaskAttemptRecord, claim.task_attempt_id)
            if attempt is None:
                raise RuntimeError("unknown-outcome attempt disappeared before commit")
            await self._sync_lifecycle(uow, attempt.workflow_step_id, now)
            await uow.commit()
            return True

    async def claim_outcome_unknown(
        self,
        attempt_id: str,
        worker_id: str,
        now: datetime,
        lease_duration: timedelta,
    ) -> ExecutionClaimRecord | None:
        """Fence one reconciler before it invokes a capability check externally."""
        worker_id = require_worker_id(worker_id)
        async with self._uow_factory.transaction() as uow:
            candidate = await uow.session.get(TaskAttemptRecord, attempt_id)
            if (
                candidate is None
                or candidate.status != TaskAttemptStatus.OUTCOME_UNKNOWN
            ):
                return None
            claim_id = str(uuid.uuid4())
            token = await uow.session.scalar(
                update(TaskAttemptRecord)
                .where(
                    TaskAttemptRecord.id == attempt_id,
                    TaskAttemptRecord.status == TaskAttemptStatus.OUTCOME_UNKNOWN,
                    TaskAttemptRecord.current_claim_id.is_(None),
                    TaskAttemptRecord.claim_fencing_token
                    == candidate.claim_fencing_token,
                )
                .values(
                    current_claim_id=claim_id,
                    claim_fencing_token=TaskAttemptRecord.claim_fencing_token + 1,
                    updated_at=now,
                )
                .returning(TaskAttemptRecord.claim_fencing_token)
            )
            if token is None:
                return None
            claim = ExecutionClaimRecord(
                id=claim_id,
                task_attempt_id=attempt_id,
                fencing_token=token,
                claimed_by=worker_id,
                purpose=ExecutionClaimPurpose.RECONCILIATION,
                claimed_at=now,
                lease_expires_at=now + lease_duration,
                status=ExecutionClaimStatus.ACTIVE,
            )
            uow.session.add(claim)
            await uow.session.flush()
            await self._sync_lifecycle(uow, candidate.workflow_step_id, now)
            await uow.commit()
            return claim

    async def return_outcome_unknown(
        self, claim: ExecutionClaimRecord, *, now: datetime
    ) -> bool:
        """Safely release a failed reconciler so a restarted process can retry it."""
        active_claim = self._active_claim(claim, now)
        async with self._uow_factory.transaction() as uow:
            restored = await uow.session.execute(
                update(TaskAttemptRecord)
                .where(
                    TaskAttemptRecord.id == claim.task_attempt_id,
                    TaskAttemptRecord.status == TaskAttemptStatus.OUTCOME_UNKNOWN,
                    TaskAttemptRecord.current_claim_id == claim.id,
                    TaskAttemptRecord.claim_fencing_token == claim.fencing_token,
                    active_claim,
                )
                .values(
                    current_claim_id=None,
                    updated_at=now,
                )
            )
            if restored.rowcount != 1:
                return False
            released = await uow.session.execute(
                update(ExecutionClaimRecord)
                .where(
                    ExecutionClaimRecord.id == claim.id,
                    ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
                )
                .values(status=ExecutionClaimStatus.RELEASED, released_at=now)
            )
            if released.rowcount != 1:
                raise RuntimeError(
                    "claim ownership changed during reconciliation rollback"
                )
            attempt = await uow.session.get(TaskAttemptRecord, claim.task_attempt_id)
            if attempt is None:
                raise RuntimeError("ambiguous attempt disappeared before commit")
            await self._sync_lifecycle(uow, attempt.workflow_step_id, now)
            await uow.commit()
            return True

    async def fail_terminal(
        self, claim: ExecutionClaimRecord, *, reason: str, now: datetime
    ) -> bool:
        """Terminalize a fenced attempt without creating another execution attempt."""
        reason = normalize_failure_code(reason)
        active_claim = self._active_claim(claim, now)
        async with self._uow_factory.transaction() as uow:
            failed = await uow.session.execute(
                update(TaskAttemptRecord)
                .where(
                    TaskAttemptRecord.id == claim.task_attempt_id,
                    TaskAttemptRecord.status.in_(
                        (TaskAttemptStatus.RUNNING, TaskAttemptStatus.OUTCOME_UNKNOWN)
                    ),
                    TaskAttemptRecord.current_claim_id == claim.id,
                    TaskAttemptRecord.claim_fencing_token == claim.fencing_token,
                    active_claim,
                )
                .values(
                    status=TaskAttemptStatus.FAILED,
                    failure_code=reason,
                    current_claim_id=None,
                    finished_at=now,
                    updated_at=now,
                )
            )
            if failed.rowcount != 1:
                return False
            released = await uow.session.execute(
                update(ExecutionClaimRecord)
                .where(
                    ExecutionClaimRecord.id == claim.id,
                    ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
                )
                .values(status=ExecutionClaimStatus.RELEASED, released_at=now)
            )
            if released.rowcount != 1:
                raise RuntimeError("claim ownership changed during terminal failure")
            attempt = await uow.session.get(TaskAttemptRecord, claim.task_attempt_id)
            if attempt is None:
                raise RuntimeError("failed attempt disappeared before commit")
            await self._sync_lifecycle(uow, attempt.workflow_step_id, now)
            await uow.commit()
            return True

    async def fail_or_retry(
        self,
        claim: ExecutionClaimRecord,
        *,
        reason: str,
        policy_id: str,
        policy_version: int,
        not_before: datetime | None,
        now: datetime,
    ) -> TaskAttemptRecord | None:
        """Terminalize the owned attempt and append an immutable retry atomically."""
        reason, policy_id, policy_version = normalize_retry_metadata(
            reason, policy_id, policy_version
        )
        active_claim = self._active_claim(claim, now)
        async with self._uow_factory.transaction() as uow:
            current_attempt = await uow.session.get(
                TaskAttemptRecord, claim.task_attempt_id
            )
            if current_attempt is None:
                return None
            max_attempts = await uow.session.scalar(
                select(WorkflowRunRecord.max_attempts)
                .join(
                    WorkflowStepRecord,
                    WorkflowStepRecord.workflow_run_id == WorkflowRunRecord.id,
                )
                .where(WorkflowStepRecord.id == current_attempt.workflow_step_id)
            )
            if max_attempts is None:
                raise RuntimeError("workflow retry budget is missing")
            failed = await uow.session.execute(
                update(TaskAttemptRecord)
                .where(
                    TaskAttemptRecord.id == claim.task_attempt_id,
                    TaskAttemptRecord.status.in_(
                        (TaskAttemptStatus.RUNNING, TaskAttemptStatus.OUTCOME_UNKNOWN)
                    ),
                    TaskAttemptRecord.current_claim_id == claim.id,
                    TaskAttemptRecord.claim_fencing_token == claim.fencing_token,
                    active_claim,
                )
                .values(
                    status=TaskAttemptStatus.FAILED,
                    failure_code=reason,
                    current_claim_id=None,
                    finished_at=now,
                    updated_at=now,
                )
            )
            if failed.rowcount != 1:
                return None
            released = await uow.session.execute(
                update(ExecutionClaimRecord)
                .where(
                    ExecutionClaimRecord.id == claim.id,
                    ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
                )
                .values(status=ExecutionClaimStatus.RELEASED, released_at=now)
            )
            if released.rowcount != 1:
                raise RuntimeError("claim ownership changed during retry scheduling")
            if current_attempt.attempt_number >= max_attempts:
                await self._sync_lifecycle(uow, current_attempt.workflow_step_id, now)
                await uow.commit()
                return None
            retry = await uow.workflows.schedule_retry(
                claim.task_attempt_id,
                retry_reason=reason,
                retry_policy_id=policy_id,
                retry_policy_version=policy_version,
                not_before=not_before,
            )
            await self._sync_lifecycle(uow, current_attempt.workflow_step_id, now)
            await uow.commit()
            return retry

    async def _reconcile_one_expired_claim(self, claim_id: str, now: datetime) -> bool:
        """Recover one ownership record in its own short transaction."""
        async with self._uow_factory.transaction() as uow:
            claim = await uow.session.get(ExecutionClaimRecord, claim_id)
            if (
                claim is None
                or claim.status != ExecutionClaimStatus.ACTIVE
                or claim.lease_expires_at > now
            ):
                return False
            attempt = await uow.session.get(TaskAttemptRecord, claim.task_attempt_id)
            if attempt is None:
                return False
            ambiguous_intent = bool(
                attempt.execution_intent_active
                and _requires_reconciliation(
                    attempt.side_effect_class,
                    attempt.idempotency_class,
                )
            )
            recovered_status = (
                TaskAttemptStatus.OUTCOME_UNKNOWN
                if claim.purpose == ExecutionClaimPurpose.RECONCILIATION
                or ambiguous_intent
                else TaskAttemptStatus.PENDING
            )
            still_current = exists().where(
                ExecutionClaimRecord.id == claim.id,
                ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
                ExecutionClaimRecord.lease_expires_at <= now,
                (ExecutionClaimRecord.recovery_not_before.is_(None))
                | (ExecutionClaimRecord.recovery_not_before <= now),
            )
            restored = await uow.session.execute(
                update(TaskAttemptRecord)
                .where(
                    TaskAttemptRecord.id == claim.task_attempt_id,
                    TaskAttemptRecord.status
                    == (
                        TaskAttemptStatus.OUTCOME_UNKNOWN
                        if claim.purpose == ExecutionClaimPurpose.RECONCILIATION
                        else TaskAttemptStatus.RUNNING
                    ),
                    TaskAttemptRecord.current_claim_id == claim.id,
                    TaskAttemptRecord.claim_fencing_token == claim.fencing_token,
                    still_current,
                )
                .values(
                    status=recovered_status,
                    current_claim_id=None,
                    execution_intent_active=False,
                    updated_at=now,
                )
            )
            if restored.rowcount != 1:
                return False
            expired = await uow.session.execute(
                update(ExecutionClaimRecord)
                .where(
                    ExecutionClaimRecord.id == claim.id,
                    ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
                    ExecutionClaimRecord.lease_expires_at <= now,
                    (ExecutionClaimRecord.recovery_not_before.is_(None))
                    | (ExecutionClaimRecord.recovery_not_before <= now),
                )
                .values(status=ExecutionClaimStatus.EXPIRED, released_at=now)
            )
            if expired.rowcount != 1:
                raise RuntimeError("claim ownership changed during reconciliation")
            recovered_attempt = await uow.session.get(
                TaskAttemptRecord, claim.task_attempt_id
            )
            if recovered_attempt is None:
                raise RuntimeError("recovered attempt disappeared before commit")
            await self._sync_lifecycle(uow, recovered_attempt.workflow_step_id, now)
            await uow.commit()
            return True

    async def _defer_failed_recovery(
        self, claim_id: str, now: datetime, recovery_backoff_seconds: int
    ) -> tuple[str, str] | None:
        """Persist a non-authorizing recovery disposition in a separate transaction."""
        async with self._uow_factory.transaction() as uow:
            claim = await uow.session.get(ExecutionClaimRecord, claim_id)
            if (
                claim is None
                or claim.status != ExecutionClaimStatus.ACTIVE
                or claim.lease_expires_at > now
                or (
                    claim.recovery_not_before is not None
                    and claim.recovery_not_before > now
                )
            ):
                return None
            deferred = await uow.session.execute(
                update(ExecutionClaimRecord)
                .where(
                    ExecutionClaimRecord.id == claim_id,
                    ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
                    ExecutionClaimRecord.lease_expires_at <= now,
                    (ExecutionClaimRecord.recovery_not_before.is_(None))
                    | (ExecutionClaimRecord.recovery_not_before <= now),
                )
                .values(
                    recovery_not_before=now
                    + timedelta(seconds=recovery_backoff_seconds),
                    recovery_failure_count=ExecutionClaimRecord.recovery_failure_count
                    + 1,
                    last_recovery_error_code=_RECOVERY_ERROR_CODE,
                )
            )
            if deferred.rowcount != 1:
                return None
            attempt = await uow.session.get(TaskAttemptRecord, claim.task_attempt_id)
            if attempt is None:
                raise RuntimeError(
                    "recovery attempt disappeared before deferral commit"
                )
            await uow.commit()
            return claim.id, attempt.id

    async def reconcile_expired_claims(
        self,
        now: datetime,
        *,
        batch_size: int = _DEFAULT_RECOVERY_BATCH_SIZE,
        recovery_backoff_seconds: int = _DEFAULT_RECOVERY_BACKOFF_SECONDS,
    ) -> int:
        """Recover a bounded, deterministic page without holding the backlog lock."""
        batch_size = validate_recovery_batch_size(batch_size)
        recovery_backoff_seconds = validate_recovery_backoff_seconds(
            recovery_backoff_seconds
        )
        async with self._uow_factory.transaction() as uow:
            claim_ids = list(
                (
                    await uow.session.scalars(
                        select(ExecutionClaimRecord.id)
                        .where(
                            ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
                            ExecutionClaimRecord.lease_expires_at <= now,
                            (ExecutionClaimRecord.recovery_not_before.is_(None))
                            | (ExecutionClaimRecord.recovery_not_before <= now),
                        )
                        .order_by(
                            ExecutionClaimRecord.lease_expires_at,
                            ExecutionClaimRecord.id,
                        )
                        .limit(batch_size)
                    )
                ).all()
            )
        recovered = 0
        for claim_id in claim_ids:
            try:
                if await self._reconcile_one_expired_claim(claim_id, now):
                    recovered += 1
            except Exception:
                try:
                    deferred = await self._defer_failed_recovery(
                        claim_id, now, recovery_backoff_seconds
                    )
                except Exception:
                    logger.warning(
                        "workflow recovery disposition unavailable claim_id=%s code=%s",
                        claim_id,
                        _RECOVERY_ERROR_CODE,
                    )
                else:
                    if deferred is not None:
                        deferred_claim_id, task_attempt_id = deferred
                        logger.warning(
                            "workflow recovery deferred claim_id=%s task_attempt_id=%s code=%s",
                            deferred_claim_id,
                            task_attempt_id,
                            _RECOVERY_ERROR_CODE,
                        )
        return recovered
