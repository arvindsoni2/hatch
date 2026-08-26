"""SQLite-backed runtime repositories sharing one transaction-scoped session."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, AsyncIterator

from sqlalchemy import delete, or_, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..evaluation.models import (
    EvaluationRunRecord,
    EvidenceObservationRecord,
    ExecutionRecord,
    PolicyDecisionRecord,
    RoutingDecisionRecord,
    ShadowComparisonRecord,
    ValidationResultRecord,
)
from ..events.outbox import SQLiteOutboxRepository
from ..events.repository import SQLiteEventRepository, enforce_metadata_only
from ..workflow.models import (
    ApprovalRecord,
    ApprovalStatus,
    TaskAttemptRecord,
    TaskAttemptStatus,
    WaitingReason,
    WorkflowRunRecord,
    WorkflowStepRecord,
)
from ..workflow.retry import normalize_retry_metadata


class _SessionBoundStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _add(self, record: Any) -> Any:
        self.session.add(record)
        await self.session.flush()
        return record


class SQLiteWorkflowStore(_SessionBoundStore):
    async def create_run(self, **values: Any) -> WorkflowRunRecord:
        enforce_metadata_only(values.get("input_ref_json") or {}, path="input_ref")
        enforce_metadata_only(values.get("result_ref_json") or {}, path="result_ref")
        return await self._add(WorkflowRunRecord(**values))

    async def create_step(self, **values: Any) -> WorkflowStepRecord:
        return await self._add(WorkflowStepRecord(**values))

    async def create_attempt(self, **values: Any) -> TaskAttemptRecord:
        enforce_metadata_only(values.get("result_ref_json") or {}, path="result_ref")
        return await self._add(TaskAttemptRecord(**values))

    async def get_attempt(self, attempt_id: str) -> TaskAttemptRecord | None:
        return await self.session.get(TaskAttemptRecord, attempt_id)

    async def schedule_retry(
        self,
        attempt_id: str,
        *,
        retry_reason: str,
        retry_policy_id: str,
        retry_policy_version: int,
        not_before: datetime | None = None,
    ) -> TaskAttemptRecord:
        retry_reason, retry_policy_id, retry_policy_version = normalize_retry_metadata(
            retry_reason, retry_policy_id, retry_policy_version
        )
        prior = await self.get_attempt(attempt_id)
        if prior is None:
            raise LookupError(f"task attempt not found: {attempt_id}")
        retry = TaskAttemptRecord(
            workflow_step_id=prior.workflow_step_id,
            attempt_number=prior.attempt_number + 1,
            prior_attempt_id=prior.id,
            status=(
                TaskAttemptStatus.WAITING if not_before else TaskAttemptStatus.PENDING
            ),
            waiting_reason=WaitingReason.RETRY_TIME if not_before else None,
            not_before=not_before,
            retry_reason=retry_reason,
            retry_policy_id=retry_policy_id,
            retry_policy_version=retry_policy_version,
        )
        return await self._add(retry)


class SQLiteApprovalStore(_SessionBoundStore):
    async def request(self, **values: Any) -> ApprovalRecord:
        return await self._add(ApprovalRecord(**values))

    async def decide(
        self,
        approval_id: str,
        *,
        status: str,
        decided_by: str,
        decision_reason: str | None = None,
        decided_at: datetime | None = None,
    ) -> bool:
        result = await self.session.execute(
            update(ApprovalRecord)
            .where(
                ApprovalRecord.id == approval_id,
                ApprovalRecord.status == ApprovalStatus.PENDING,
                or_(
                    ApprovalRecord.expires_at.is_(None),
                    ApprovalRecord.expires_at > (decided_at or datetime.utcnow()),
                ),
            )
            .values(
                status=status,
                decided_by=decided_by,
                decision_reason=decision_reason,
                decided_at=decided_at or datetime.utcnow(),
            )
        )
        return result.rowcount == 1

    async def expire_if_due(self, approval_id: str, *, now: datetime) -> bool:
        result = await self.session.execute(
            update(ApprovalRecord)
            .where(
                ApprovalRecord.id == approval_id,
                ApprovalRecord.status == ApprovalStatus.PENDING,
                ApprovalRecord.expires_at.is_not(None),
                ApprovalRecord.expires_at <= now,
            )
            .values(
                status=ApprovalStatus.EXPIRED,
                decided_at=now,
                decision_reason="expired",
            )
        )
        return result.rowcount == 1

    async def invalidate_for_payload_change(
        self, task_attempt_id: str, *, current_payload_hash: str, now: datetime
    ) -> int:
        result = await self.session.execute(
            update(ApprovalRecord)
            .where(
                ApprovalRecord.task_attempt_id == task_attempt_id,
                ApprovalRecord.status.in_(
                    (ApprovalStatus.PENDING, ApprovalStatus.APPROVED)
                ),
                ApprovalRecord.payload_hash != current_payload_hash,
            )
            .values(
                status=ApprovalStatus.INVALIDATED,
                decided_at=now,
                decision_reason="payload_changed",
            )
        )
        return result.rowcount


class SQLiteEvaluationStore(_SessionBoundStore):
    async def _record(self, record_type: type[Any], **values: Any) -> Any:
        for field in (
            "metadata_json",
            "reason_codes_json",
            "result_json",
            "observation_json",
        ):
            enforce_metadata_only(values.get(field) or {}, path=field)
        return await self._add(record_type(**values))

    async def record_policy_decision(self, **values: Any) -> PolicyDecisionRecord:
        return await self._record(PolicyDecisionRecord, **values)

    async def record_routing_decision(self, **values: Any) -> RoutingDecisionRecord:
        return await self._record(RoutingDecisionRecord, **values)

    async def record_execution(self, **values: Any) -> ExecutionRecord:
        return await self._record(ExecutionRecord, **values)

    async def record_validation(self, **values: Any) -> ValidationResultRecord:
        return await self._record(ValidationResultRecord, **values)

    async def record_evaluation(self, **values: Any) -> EvaluationRunRecord:
        return await self._record(EvaluationRunRecord, **values)

    async def record_observation(self, **values: Any) -> EvidenceObservationRecord:
        return await self._record(EvidenceObservationRecord, **values)


class SQLiteShadowComparisonStore(_SessionBoundStore):
    async def record(self, **values: Any) -> ShadowComparisonRecord:
        enforce_metadata_only(values.get("metrics_json") or {}, path="metrics")
        created_at = values.pop("created_at", None) or datetime.utcnow()
        expires_at = values.pop("expires_at", None) or created_at + timedelta(days=30)
        if expires_at > created_at + timedelta(days=30):
            raise ValueError("shadow comparison retention cannot exceed 30 days")
        return await self._add(
            ShadowComparisonRecord(
                **values,
                created_at=created_at,
                expires_at=expires_at,
            )
        )

    async def purge_expired(self, *, now: datetime | None = None) -> int:
        result = await self.session.execute(
            delete(ShadowComparisonRecord).where(
                ShadowComparisonRecord.expires_at <= (now or datetime.utcnow())
            )
        )
        return result.rowcount


class SQLiteRuntimeUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.workflows = SQLiteWorkflowStore(session)
        self.approvals = SQLiteApprovalStore(session)
        self.events = SQLiteEventRepository(session)
        self.outbox = SQLiteOutboxRepository(session)
        self.evaluations = SQLiteEvaluationStore(session)
        self.shadow = SQLiteShadowComparisonStore(session)
        self._committed = False

    async def commit(self) -> None:
        await self.session.commit()
        self._committed = True

    async def rollback(self) -> None:
        await self.session.rollback()
        self._committed = False


class SQLiteRuntimeUnitOfWorkFactory:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SQLiteRuntimeUnitOfWork]:
        async with self.session_factory() as session:
            uow = SQLiteRuntimeUnitOfWork(session)
            try:
                yield uow
            except BaseException:
                await uow.rollback()
                raise
