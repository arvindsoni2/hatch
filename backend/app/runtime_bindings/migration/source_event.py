"""Reconcile product event acknowledgements with authoritative NEW score runs."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_event import AgentEvent
from app.runtime.workflow.models import WorkflowRunRecord

from ..tasks.job_score import JOB_SCORE_V1


async def reconcile_job_score_source_event(
    event_id: str, db: AsyncSession
) -> str | None:
    """Return scored/skipped/runtime_owned, or None for an unbound source.

    An event status is only a delivery acknowledgement, not authority to start
    another runtime lifecycle. Match task, mode, source and job before using a
    durable run. The caller commits the acknowledgement in its transaction.
    """
    source = await db.get(AgentEvent, event_id, populate_existing=True)
    if source is None or source.event_type != "job_discovered":
        return None
    try:
        payload = json.loads(source.payload)
    except (TypeError, ValueError):
        payload = None
    job_ref = (
        f"job:{payload['job_id']}"
        if isinstance(payload, dict) and isinstance(payload.get("job_id"), str)
        else None
    )
    runs = list(
        await db.scalars(
            select(WorkflowRunRecord)
            .where(
                WorkflowRunRecord.workflow_definition_id == JOB_SCORE_V1.task_id,
                WorkflowRunRecord.workflow_definition_version == JOB_SCORE_V1.version,
                WorkflowRunRecord.runtime_mode == "new",
                WorkflowRunRecord.input_ref_json["event_ref"].as_string()
                == f"event:{event_id}",
            )
            .limit(2)
        )
    )
    if not runs:
        return None
    if len(runs) != 1 or any(
        run.domain_type != "job_posting"
        or run.domain_id != job_ref
        or run.input_ref_json.get("job_ref") != job_ref
        for run in runs
    ):
        await db.execute(
            update(AgentEvent)
            .where(AgentEvent.id == event_id)
            .values(status="failed", error_message="job_score_source_identity_conflict")
        )
        return "runtime_owned"
    completed = next((run for run in runs if run.status == "completed"), None)
    if completed is not None:
        await db.execute(
            update(AgentEvent)
            .where(AgentEvent.id == event_id)
            .values(
                status="completed",
                processed_at=completed.completed_at or datetime.utcnow(),
                error_message=None,
            )
        )
        return (
            "skipped"
            if (completed.result_ref_json or {}).get("reason_code")
            == "job_score_irrelevant"
            else "scored"
        )
    # Recovery/retry stays with the existing runtime attempt and policy. Never
    # let a stale product failure flag grant permission for a fresh run.
    active = any(run.status not in {"failed", "cancelled"} for run in runs)
    await db.execute(
        update(AgentEvent)
        .where(AgentEvent.id == event_id, AgentEvent.status != "completed")
        .values(
            status="processing" if active else "failed",
            error_message=None if active else "job_score_runtime_failed",
        )
    )
    return "runtime_owned"
