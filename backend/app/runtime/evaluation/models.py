"""ORM records for policy, routing, execution, validation, and evidence."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from ...database import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.utcnow()


class ExecutionRole(str, Enum):
    PRIMARY = "primary"
    REPAIR = "repair"
    FALLBACK = "fallback"
    EVALUATOR = "evaluator"
    TOOL = "tool"
    ARTIFACT = "artifact"
    RECONCILIATION = "reconciliation"


class PolicyDecisionRecord(Base):
    __tablename__ = "runtime_policy_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_attempt_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_task_attempts.id"), nullable=False
    )
    policy_id: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(128))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class RoutingDecisionRecord(Base):
    __tablename__ = "runtime_routing_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_attempt_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_task_attempts.id"), nullable=False
    )
    router_id: Mapped[str] = mapped_column(String(128), nullable=False)
    router_version: Mapped[int] = mapped_column(Integer, nullable=False)
    capability_id: Mapped[str] = mapped_column(String(128), nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(128))
    provider: Mapped[str | None] = mapped_column(String(64))
    reason_codes_json: Mapped[list[str] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ExecutionRecord(Base):
    __tablename__ = "runtime_execution_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_attempt_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_task_attempts.id"), nullable=False
    )
    parent_execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("runtime_execution_records.id")
    )
    execution_role: Mapped[str] = mapped_column(String(24), nullable=False)
    capability_id: Mapped[str] = mapped_column(String(128), nullable=False)
    capability_version: Mapped[int] = mapped_column(Integer, nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(128))
    model_version: Mapped[str | None] = mapped_column(String(128))
    provider: Mapped[str | None] = mapped_column(String(64))
    strategy_stage: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    result_class: Mapped[str] = mapped_column(String(32), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    span_id: Mapped[str | None] = mapped_column(String(32))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class ValidationResultRecord(Base):
    __tablename__ = "runtime_validation_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_attempt_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_task_attempts.id"), nullable=False
    )
    execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("runtime_execution_records.id")
    )
    validator_id: Mapped[str] = mapped_column(String(128), nullable=False)
    validator_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    reason_codes_json: Mapped[list[str] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class EvaluationRunRecord(Base):
    __tablename__ = "runtime_evaluation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_attempt_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_task_attempts.id"), nullable=False
    )
    execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("runtime_execution_records.id")
    )
    evaluator_id: Mapped[str] = mapped_column(String(128), nullable=False)
    evaluator_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class EvidenceObservationRecord(Base):
    __tablename__ = "runtime_evidence_observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    evaluation_run_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_evaluation_runs.id"), nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    observation_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ModelEvidenceRecord(Base):
    __tablename__ = "runtime_model_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    task_version: Mapped[int] = mapped_column(Integer, nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)


class ContextPackageRecord(Base):
    __tablename__ = "runtime_context_packages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_attempt_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_task_attempts.id"), nullable=False
    )
    package_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False)
    sensitivity_max: Mapped[str] = mapped_column(String(24), nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    items_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)


class ShadowComparisonRecord(Base):
    __tablename__ = "runtime_shadow_comparisons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    slice_name: Mapped[str] = mapped_column(String(64), nullable=False)
    domain_type: Mapped[str] = mapped_column(String(64), nullable=False)
    domain_id_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    legacy_execution_ref: Mapped[str | None] = mapped_column(String(128))
    runtime_execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("runtime_execution_records.id")
    )
    legacy_result_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    runtime_result_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    comparison_status: Mapped[str] = mapped_column(String(32), nullable=False)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
