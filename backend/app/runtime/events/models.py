"""Append-only event and transactional outbox ORM records."""

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
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ...database import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.utcnow()


class RuntimeActorType(str, Enum):
    USER = "user"
    SYSTEM = "system"
    WORKER = "worker"
    MODEL = "model"
    CAPABILITY = "capability"
    RECONCILER = "reconciler"


class RuntimeOutboxStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    RETRY_WAIT = "retry_wait"
    DELIVERED = "delivered"
    DEAD_LETTER = "dead_letter"


class RuntimeEventRecord(Base):
    __tablename__ = "runtime_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    workflow_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("runtime_workflow_runs.id")
    )
    workflow_step_id: Mapped[str | None] = mapped_column(
        ForeignKey("runtime_workflow_steps.id")
    )
    task_attempt_id: Mapped[str | None] = mapped_column(
        ForeignKey("runtime_task_attempts.id")
    )
    actor_type: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(128))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    causation_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("runtime_events.id")
    )
    sensitivity: Mapped[str] = mapped_column(String(24), nullable=False)


class RuntimeOutboxRecord(Base):
    __tablename__ = "runtime_outbox"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_events.id"), nullable=False
    )
    destination: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default=RuntimeOutboxStatus.PENDING, server_default="pending"
    )
    not_before: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    claim_id: Mapped[str | None] = mapped_column(String(36))
    fencing_token: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )


class RuntimeOutboxAttemptRecord(Base):
    __tablename__ = "runtime_outbox_attempts"
    __table_args__ = (
        UniqueConstraint(
            "outbox_entry_id", "attempt_number", name="uq_runtime_outbox_attempt"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    outbox_entry_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_outbox.id"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_detail: Mapped[str | None] = mapped_column(Text)
