"""Short transactional persistence operations for durable workflow ownership."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
import re

from sqlalchemy import exists, select, update

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
    WorkflowStepRecord,
)
from .retry import normalize_retry_metadata


_RECONCILIATION_CODE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_IDEMPOTENCY_CLASSES = {
    "idempotent",
    "idempotent_with_key",
    "check_before_retry",
    "non_retryable_side_effect",
}


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


class SQLiteWorkflowRepository:
    """Durable workflow operations, each enclosed in a small database transaction."""

    def __init__(self, uow_factory: RuntimeUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def create_run(
        self,
        *,
        workflow_definition_id: str,
        workflow_definition_version: int,
        input_ref: dict[str, object],
        domain_ref: dict[str, object],
        mode: str,
        max_attempts: int,
    ):
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

    async def transition_waiting(
        self,
        claim: ExecutionClaimRecord,
        *,
        reason: WaitingReason,
        now: datetime,
    ) -> bool:
        """Release only the current fenced owner into a durable wait state."""
        active_claim = exists().where(
            ExecutionClaimRecord.id == claim.id,
            ExecutionClaimRecord.task_attempt_id == claim.task_attempt_id,
            ExecutionClaimRecord.fencing_token == claim.fencing_token,
            ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
        )
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
            await uow.commit()
            return attempt

    async def _claim_pending(
        self, worker_id: str, now: datetime, lease_duration: timedelta
    ) -> ExecutionClaimRecord | None:
        async with self._uow_factory.transaction() as uow:
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
                return None
            claim_id = str(uuid.uuid4())
            lease_expires_at = now + lease_duration
            token = await uow.session.scalar(
                update(TaskAttemptRecord)
                .where(
                    TaskAttemptRecord.id == candidate.id,
                    TaskAttemptRecord.status == TaskAttemptStatus.PENDING,
                    TaskAttemptRecord.claim_fencing_token == candidate.claim_fencing_token,
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
                )
            )
            if previous is None:
                return None
            claim_id = str(uuid.uuid4())
            lease_expires_at = now + lease_duration
            token = await uow.session.scalar(
                update(TaskAttemptRecord)
                .where(
                    TaskAttemptRecord.id == attempt_id,
                    TaskAttemptRecord.status == TaskAttemptStatus.RUNNING,
                    TaskAttemptRecord.current_claim_id == previous.id,
                    TaskAttemptRecord.claim_fencing_token == previous.fencing_token,
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
            await uow.session.execute(
                update(ExecutionClaimRecord)
                .where(
                    ExecutionClaimRecord.id == previous.id,
                    ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
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
        active_claim = exists().where(
            ExecutionClaimRecord.id == claim.id,
            ExecutionClaimRecord.task_attempt_id == claim.task_attempt_id,
            ExecutionClaimRecord.fencing_token == claim.fencing_token,
            ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
        )
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
        capability_id, capability_version, idempotency_class, reconciliation_reference = (
            normalize_reconciliation_binding(
                capability_id,
                capability_version,
                idempotency_class,
                reconciliation_reference,
            )
        )
        active_claim = exists().where(
            ExecutionClaimRecord.id == claim.id,
            ExecutionClaimRecord.task_attempt_id == claim.task_attempt_id,
            ExecutionClaimRecord.fencing_token == claim.fencing_token,
            ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
        )
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
                raise RuntimeError("claim ownership changed during unknown-outcome transition")
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
            if candidate is None or candidate.status != TaskAttemptStatus.OUTCOME_UNKNOWN:
                return None
            claim_id = str(uuid.uuid4())
            token = await uow.session.scalar(
                update(TaskAttemptRecord)
                .where(
                    TaskAttemptRecord.id == attempt_id,
                    TaskAttemptRecord.status == TaskAttemptStatus.OUTCOME_UNKNOWN,
                    TaskAttemptRecord.current_claim_id.is_(None),
                    TaskAttemptRecord.claim_fencing_token == candidate.claim_fencing_token,
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
            await uow.commit()
            return claim

    async def return_outcome_unknown(
        self, claim: ExecutionClaimRecord, *, now: datetime
    ) -> bool:
        """Safely release a failed reconciler so a restarted process can retry it."""
        active_claim = exists().where(
            ExecutionClaimRecord.id == claim.id,
            ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
        )
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
                .values(current_claim_id=None,
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
                raise RuntimeError("claim ownership changed during reconciliation rollback")
            await uow.commit()
            return True

    async def fail_terminal(
        self, claim: ExecutionClaimRecord, *, reason: str, now: datetime
    ) -> bool:
        """Terminalize a fenced attempt without creating another execution attempt."""
        active_claim = exists().where(
            ExecutionClaimRecord.id == claim.id,
            ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
        )
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
        active_claim = exists().where(
            ExecutionClaimRecord.id == claim.id,
            ExecutionClaimRecord.task_attempt_id == claim.task_attempt_id,
            ExecutionClaimRecord.fencing_token == claim.fencing_token,
            ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
        )
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
                await uow.commit()
                return None
            retry = await uow.workflows.schedule_retry(
                claim.task_attempt_id,
                retry_reason=reason,
                retry_policy_id=policy_id,
                retry_policy_version=policy_version,
                not_before=not_before,
            )
            await uow.commit()
            return retry

    async def reconcile_expired_claims(self, now: datetime) -> int:
        """Release abandoned ownership without relying on a process-local registry."""
        recovered = 0
        async with self._uow_factory.transaction() as uow:
            expired_claims = list(
                (
                    await uow.session.scalars(
                        select(ExecutionClaimRecord).where(
                            ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
                            ExecutionClaimRecord.lease_expires_at <= now,
                        )
                    )
                ).all()
            )
            for claim in expired_claims:
                still_current = exists().where(
                    ExecutionClaimRecord.id == claim.id,
                    ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
                    ExecutionClaimRecord.lease_expires_at <= now,
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
                        status=(
                            TaskAttemptStatus.OUTCOME_UNKNOWN
                            if claim.purpose == ExecutionClaimPurpose.RECONCILIATION
                            else TaskAttemptStatus.PENDING
                        ),
                        current_claim_id=None,
                        updated_at=now,
                    )
                )
                if restored.rowcount != 1:
                    continue
                expired = await uow.session.execute(
                    update(ExecutionClaimRecord)
                    .where(
                        ExecutionClaimRecord.id == claim.id,
                        ExecutionClaimRecord.status == ExecutionClaimStatus.ACTIVE,
                    )
                    .values(status=ExecutionClaimStatus.EXPIRED, released_at=now)
                )
                if expired.rowcount != 1:
                    raise RuntimeError("claim ownership changed during reconciliation")
                recovered += 1
            if recovered:
                await uow.commit()
            return recovered
