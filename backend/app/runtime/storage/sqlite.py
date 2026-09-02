"""SQLite-backed runtime repositories sharing one transaction-scoped session."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import json
from typing import Any, AsyncIterator

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..evaluation.models import (
    ContextPackageRecord,
    EvaluationRunRecord,
    EvidenceObservationRecord,
    ExecutionRecord,
    ModelEvidenceRecord,
    PolicyDecisionRecord,
    RoutingDecisionRecord,
    ShadowComparisonRecord,
    ValidationResultRecord,
)
from ..context.models import (
    ContextItem,
    ContextOmission,
    ContextPackage,
    context_package_hash,
    validate_context_item_metadata,
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
from ..workflow.approvals import (
    normalize_approval_actor_id,
    normalize_approval_decision_status,
    normalize_approval_store_values,
    normalize_decision_reason,
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
        normalize_approval_store_values(values)
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
        status = normalize_approval_decision_status(status)
        decided_by = normalize_approval_actor_id(decided_by)
        decision_reason = normalize_decision_reason(decision_reason)
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
            "candidate_snapshot_json",
            "metrics_json",
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

    async def record_model_evidence(self, **values: Any) -> ModelEvidenceRecord:
        """Persist only evidence that an explicit qualification already promoted."""
        if values.get("metrics_json", {}) not in ({}, None):
            raise ValueError("model evidence accepts typed metadata only")
        return await self._record(ModelEvidenceRecord, **values)

    async def load_model_evidence(self) -> list[ModelEvidenceRecord]:
        return list((await self.session.scalars(select(ModelEvidenceRecord))).all())


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


class SQLiteContextPackageStore(_SessionBoundStore):
    """Persist context metadata and bind it to an attempt in the caller's UoW."""

    async def persist_and_bind(self, package: ContextPackage) -> None:
        for item in package.items:
            validate_context_item_metadata(item)
        if (
            context_package_hash(
                package.task_attempt_id, package.items, package.omissions
            )
            != package.content_hash
        ):
            raise ValueError("context_package_corrupt")
        attempt = await self.session.get(TaskAttemptRecord, package.task_attempt_id)
        if attempt is None:
            raise ValueError("context_task_attempt_missing")
        if attempt.context_package_id is not None:
            raise ValueError("context_package_already_bound")
        sensitivity_max = max(
            (item.sensitivity for item in package.items),
            key={"public": 0, "internal": 1, "confidential": 2, "restricted": 3}.get,
            default="public",
        )
        record = ContextPackageRecord(
            id=package.id,
            task_attempt_id=package.task_attempt_id,
            package_version=1,
            content_hash=package.content_hash,
            token_estimate=package.total_token_estimate,
            sensitivity_max=sensitivity_max,
            items_json={
                "items": [item.model_dump(mode="json") for item in package.items],
                "omissions": [
                    omission.model_dump(mode="json") for omission in package.omissions
                ],
            },
        )
        self.session.add(record)
        await self.session.flush()
        result = await self.session.execute(
            update(TaskAttemptRecord)
            .where(
                TaskAttemptRecord.id == package.task_attempt_id,
                TaskAttemptRecord.context_package_id.is_(None),
            )
            .values(context_package_id=package.id)
        )
        if result.rowcount != 1:
            await self.session.delete(record)
            await self.session.flush()
            raise ValueError("context_package_already_bound")

    async def load(self, package_id: str) -> ContextPackage | None:
        record = await self.session.get(ContextPackageRecord, package_id)
        if record is None:
            return None
        serialized = record.items_json
        if isinstance(serialized, list):
            item_rows, omission_rows = serialized, []
        else:
            item_rows = serialized.get("items", [])
            omission_rows = serialized.get("omissions", [])
        items = tuple(
            ContextItem.model_validate_json(json.dumps(item)) for item in item_rows
        )
        omissions = tuple(
            ContextOmission.model_validate_json(json.dumps(omission))
            for omission in omission_rows
        )
        if (
            context_package_hash(record.task_attempt_id, items, omissions)
            != record.content_hash
        ):
            raise ValueError("context_package_corrupt")
        return ContextPackage(
            id=record.id,
            task_attempt_id=record.task_attempt_id,
            items=items,
            omissions=omissions,
            total_token_estimate=record.token_estimate,
            content_hash=record.content_hash,
        )


class SQLiteRuntimeUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.workflows = SQLiteWorkflowStore(session)
        self.approvals = SQLiteApprovalStore(session)
        self.events = SQLiteEventRepository(session)
        self.outbox = SQLiteOutboxRepository(session)
        self.evaluations = SQLiteEvaluationStore(session)
        self.shadow = SQLiteShadowComparisonStore(session)
        self.context_packages = SQLiteContextPackageStore(session)
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
