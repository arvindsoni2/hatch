"""Durable primary, repair, fallback, and evaluator lineage."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.runtime.evaluation import EvaluationLineage
from app.runtime.evaluation.models import EvaluationRunRecord, ExecutionRecord
from app.runtime.storage.sqlite import SQLiteRuntimeUnitOfWorkFactory


@pytest.mark.asyncio
async def test_primary_repair_fallback_lineage_reconstructs(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'lineage.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = SQLiteRuntimeUnitOfWorkFactory(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    try:
        async with factory.transaction() as uow:
            run = await uow.workflows.create_run(
                workflow_definition_id="synthetic.evaluate",
                workflow_definition_version=1,
                domain_type="synthetic",
                runtime_mode="new",
                max_attempts=1,
            )
            step = await uow.workflows.create_step(
                workflow_run_id=run.id,
                step_key="evaluate",
                step_order=1,
                task_id="synthetic.evaluate",
                task_version=1,
            )
            attempt = await uow.workflows.create_attempt(
                workflow_step_id=step.id,
                attempt_number=1,
            )
            executions = await uow.evaluations.record_execution_lineage(
                task_attempt_id=attempt.id,
                executions=tuple(
                    {
                        "execution_role": role,
                        "capability_id": f"synthetic.{role}",
                        "capability_version": 1,
                        "model_id": "synthetic.model" if role != "primary" else None,
                        "model_version": "v1" if role != "primary" else None,
                        "provider": "synthetic" if role != "primary" else None,
                        "strategy_stage": role,
                        "started_at": now,
                        "finished_at": now,
                        "result_class": "passed",
                        "metadata_json": {},
                    }
                    for role in ("primary", "repair", "fallback", "evaluator")
                ),
            )
            lineage = EvaluationLineage(
                primary_execution_id=executions[0].id,
                repair_execution_id=executions[1].id,
                fallback_execution_id=executions[2].id,
                evaluation_execution_id=executions[3].id,
            )
            evaluation = await uow.evaluations.record_evaluation(
                task_attempt_id=attempt.id,
                execution_id=lineage.evaluation_execution_id,
                evaluation_execution_id=lineage.evaluation_execution_id,
                primary_execution_id=lineage.primary_execution_id,
                repair_execution_id=lineage.repair_execution_id,
                fallback_execution_id=lineage.fallback_execution_id,
                evaluator_id="synthetic.evaluator",
                evaluator_version=1,
                evaluator_type="deterministic",
                evaluation_spec_id="synthetic.spec",
                evaluation_spec_version=1,
                status="completed",
                result="passed",
                reason_codes_json=["schema_valid"],
                scores_json={"quality": 1.0},
                validation_metrics_json={"schema_errors": 0},
            )
            evaluation_id = evaluation.id
            await uow.commit()

        async with factory.session_factory() as session:
            stored = await session.get(EvaluationRunRecord, evaluation_id)
            assert stored is not None
            lineage_ids = (
                stored.primary_execution_id,
                stored.repair_execution_id,
                stored.fallback_execution_id,
                stored.evaluation_execution_id,
            )
            records = list(
                (
                    await session.scalars(
                        select(ExecutionRecord).where(
                            ExecutionRecord.id.in_(lineage_ids)
                        )
                    )
                ).all()
            )
            by_id = {record.id: record for record in records}
            assert [by_id[item].execution_role for item in lineage_ids] == [
                "primary",
                "repair",
                "fallback",
                "evaluator",
            ]
            assert by_id[lineage_ids[0]].parent_execution_id is None
            assert by_id[lineage_ids[1]].parent_execution_id == lineage_ids[0]
            assert by_id[lineage_ids[2]].parent_execution_id == lineage_ids[1]
            assert by_id[lineage_ids[3]].parent_execution_id == lineage_ids[2]
            assert (await session.execute(text("PRAGMA foreign_key_check"))).all() == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_execution_lineage_rejects_noncanonical_role_order(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bad-lineage.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = SQLiteRuntimeUnitOfWorkFactory(async_sessionmaker(engine))
    try:
        async with factory.transaction() as uow:
            with pytest.raises(ValueError, match="canonical order"):
                await uow.evaluations.record_execution_lineage(
                    task_attempt_id="attempt-id",
                    executions=(
                        {"execution_role": "primary"},
                        {"execution_role": "fallback"},
                    ),
                )
    finally:
        await engine.dispose()
