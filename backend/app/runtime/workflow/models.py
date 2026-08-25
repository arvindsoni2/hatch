"""SQLAlchemy records for durable workflow state and ownership."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ...database import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.utcnow()


class WorkflowRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskAttemptStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    OUTCOME_UNKNOWN = "outcome_unknown"


class ExecutionClaimStatus(str, Enum):
    ACTIVE = "active"
    RELEASED = "released"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class WaitingReason(str, Enum):
    APPROVAL = "approval"
    USER_INPUT = "user_input"
    RETRY_TIME = "retry_time"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"


class WorkflowRunRecord(Base):
    __tablename__ = "runtime_workflow_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    workflow_definition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    workflow_definition_version: Mapped[int] = mapped_column(Integer, nullable=False)
    domain_type: Mapped[str] = mapped_column(String(64), nullable=False)
    domain_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(
        String(24), default=WorkflowRunStatus.PENDING, server_default="pending"
    )
    runtime_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    input_ref_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    result_ref_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    failure_code: Mapped[str | None] = mapped_column(String(128))
    trace_id: Mapped[str | None] = mapped_column(String(64))


class WorkflowStepRecord(Base):
    __tablename__ = "runtime_workflow_steps"
    __table_args__ = (
        UniqueConstraint("workflow_run_id", "step_key", name="uq_runtime_step_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    workflow_run_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_workflow_runs.id"), nullable=False
    )
    step_key: Mapped[str] = mapped_column(String(128), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    task_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default=WorkflowStepStatus.PENDING, server_default="pending"
    )
    waiting_reason: Mapped[str | None] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    failure_code: Mapped[str | None] = mapped_column(String(128))


class TaskAttemptRecord(Base):
    __tablename__ = "runtime_task_attempts"
    __table_args__ = (
        UniqueConstraint(
            "workflow_step_id", "attempt_number", name="uq_runtime_attempt_number"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    workflow_step_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_workflow_steps.id"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    prior_attempt_id: Mapped[str | None] = mapped_column(
        ForeignKey("runtime_task_attempts.id")
    )
    status: Mapped[str] = mapped_column(
        String(24), default=TaskAttemptStatus.PENDING, server_default="pending"
    )
    waiting_reason: Mapped[str | None] = mapped_column(String(24))
    not_before: Mapped[datetime | None] = mapped_column(DateTime)
    retry_reason: Mapped[str | None] = mapped_column(String(128))
    retry_policy_id: Mapped[str | None] = mapped_column(String(128))
    retry_policy_version: Mapped[int | None] = mapped_column(Integer)
    claim_fencing_token: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    current_claim_id: Mapped[str | None] = mapped_column(String(36))
    context_package_id: Mapped[str | None] = mapped_column(String(36))
    result_ref_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    failure_code: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )


class ExecutionClaimRecord(Base):
    __tablename__ = "runtime_execution_claims"
    __table_args__ = (
        UniqueConstraint(
            "task_attempt_id", "fencing_token", name="uq_runtime_claim_fence"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_attempt_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_task_attempts.id"), nullable=False
    )
    fencing_token: Mapped[int] = mapped_column(BigInteger, nullable=False)
    claimed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    claimed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(
        String(24), default=ExecutionClaimStatus.ACTIVE, server_default="active"
    )


class ApprovalRecord(Base):
    __tablename__ = "runtime_approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    workflow_run_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_workflow_runs.id"), nullable=False
    )
    workflow_step_id: Mapped[str | None] = mapped_column(
        ForeignKey("runtime_workflow_steps.id")
    )
    task_attempt_id: Mapped[str | None] = mapped_column(
        ForeignKey("runtime_task_attempts.id")
    )
    capability_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash_algorithm: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default=ApprovalStatus.PENDING, server_default="pending"
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    decided_by: Mapped[str | None] = mapped_column(String(128))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    decision_reason: Mapped[str | None] = mapped_column(String(256))
