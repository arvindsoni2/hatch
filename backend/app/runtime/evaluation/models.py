"""ORM records for policy, routing, execution, validation, and evidence."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    JSON,
    Numeric,
    String,
)
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
    task_id: Mapped[str | None] = mapped_column(String(128))
    task_version: Mapped[int | None] = mapped_column(Integer)
    model_id: Mapped[str | None] = mapped_column(String(128))
    model_version: Mapped[str | None] = mapped_column(String(128))
    provider: Mapped[str | None] = mapped_column(String(64))
    candidate_snapshot_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    routing_policy_version: Mapped[int | None] = mapped_column(Integer)
    evidence_snapshot_id: Mapped[str | None] = mapped_column(String(128))
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
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class EvaluationRunRecord(Base):
    __tablename__ = "runtime_evaluation_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["primary_execution_id"],
            ["runtime_execution_records.id"],
            name="fk_runtime_evaluation_runs_primary_execution_id",
        ),
        ForeignKeyConstraint(
            ["repair_execution_id"],
            ["runtime_execution_records.id"],
            name="fk_runtime_evaluation_runs_repair_execution_id",
        ),
        ForeignKeyConstraint(
            ["fallback_execution_id"],
            ["runtime_execution_records.id"],
            name="fk_runtime_evaluation_runs_fallback_execution_id",
        ),
        ForeignKeyConstraint(
            ["evaluation_execution_id"],
            ["runtime_execution_records.id"],
            name="fk_runtime_evaluation_runs_evaluation_execution_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_attempt_id: Mapped[str] = mapped_column(
        ForeignKey("runtime_task_attempts.id"), nullable=False
    )
    execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("runtime_execution_records.id")
    )
    evaluation_execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("runtime_execution_records.id")
    )
    evaluator_id: Mapped[str] = mapped_column(String(128), nullable=False)
    evaluator_version: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluator_type: Mapped[str | None] = mapped_column(String(24))
    evaluation_spec_id: Mapped[str | None] = mapped_column(String(128))
    evaluation_spec_version: Mapped[int | None] = mapped_column(Integer)
    evaluator_model_id: Mapped[str | None] = mapped_column(String(128))
    evaluator_model_version: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    result: Mapped[str | None] = mapped_column(String(24))
    scores_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    reason_codes_json: Mapped[list[str] | None] = mapped_column(JSON)
    validation_metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    primary_execution_id: Mapped[str | None] = mapped_column(String(36))
    repair_execution_id: Mapped[str | None] = mapped_column(String(36))
    fallback_execution_id: Mapped[str | None] = mapped_column(String(36))
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
    routing_observation_type: Mapped[str | None] = mapped_column(String(64))
    task_id: Mapped[str | None] = mapped_column(String(128))
    task_version: Mapped[int | None] = mapped_column(Integer)
    model_id: Mapped[str | None] = mapped_column(String(128))
    model_version: Mapped[str | None] = mapped_column(String(128))
    provider: Mapped[str | None] = mapped_column(String(64))
    quality_score: Mapped[float | None] = mapped_column(Numeric(6, 5))
    sample_size: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ModelEvidenceRecord(Base):
    __tablename__ = "runtime_model_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    task_version: Mapped[int] = mapped_column(Integer, nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    qualification_id: Mapped[str | None] = mapped_column(String(128))
    qualification_version: Mapped[int | None] = mapped_column(Integer)
    minimum_sample_size: Mapped[int | None] = mapped_column(Integer)
    observation_ids_json: Mapped[list[str] | None] = mapped_column(JSON)
    quality_score: Mapped[float | None] = mapped_column(Numeric(6, 5))
    metrics_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
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
    items_json: Mapped[dict[str, Any] | list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False
    )


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
