"""Durable workflow adapter for one Job Scoring runtime execution."""

from __future__ import annotations

import hashlib
import json
import asyncio
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from decimal import Decimal
from collections.abc import Awaitable, Callable
from typing import Any
from datetime import datetime

from app.runtime.workflow import ExecutionClaimRecord, WorkflowKernel
from app.runtime.workflow.models import (
    WorkflowRunRecord,
    WorkflowStepRecord,
    TaskAttemptRecord,
)
from app.runtime import RuntimeMode
from app.runtime.contracts import ExecutionResultCode
from app.runtime.context.resolver import ContextResolutionError
from app.runtime.evaluation.models import ExecutionRecord
from app.runtime.observability import RuntimeCorrelation, RuntimeTelemetry
from sqlalchemy import select

from .scoring import RuntimeScoringOperation, ScoringUsage
from .facade import JobScoreClaimLost

from ..tasks.job_score import JOB_SCORE_V1, JobScoreInput, JobScoreOutput


def _hash_ref(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True)
class RuntimeJobScoreResult:
    output: JobScoreOutput | None
    run_id: str
    execution_id: str | None
    usage: ScoringUsage
    reason_code: str


class DurableJobScoreRuntime:
    """Binds Job Scoring to the generic fenced workflow kernel.

    It persists opaque references and output hashes only. Product code owns the
    visible JobScore projection; this adapter owns durable runtime lifecycle.
    """

    def __init__(
        self,
        kernel: WorkflowKernel,
        *,
        worker_id: str,
        factory=None,
        security_policy=None,
        plan=None,
    ) -> None:
        self._kernel = kernel
        self._worker_id = worker_id
        self._factory = factory
        self._security_policy = security_policy
        self._plan = plan

    async def start(
        self, request: JobScoreInput, *, mode: RuntimeMode = RuntimeMode.NEW
    ):
        if mode is RuntimeMode.NEW and self._factory is not None:
            # Reuse pre-idempotency rollout runs too. The event is the identity;
            # changing its job/profile cannot authorize a second lifecycle.
            async with self._factory.session_factory() as session:
                recorded = list(
                    await session.scalars(
                        select(WorkflowRunRecord)
                        .where(
                            WorkflowRunRecord.workflow_definition_id
                            == JOB_SCORE_V1.task_id,
                            WorkflowRunRecord.workflow_definition_version
                            == JOB_SCORE_V1.version,
                            WorkflowRunRecord.runtime_mode == "new",
                            WorkflowRunRecord.input_ref_json["event_ref"].as_string()
                            == request.event_ref,
                        )
                        .limit(2)
                    )
                )
            if recorded:
                if len(recorded) != 1:
                    raise ValueError("job_score_source_identity_conflict")
                run = recorded[0]
                if (
                    run.domain_type != "job_posting"
                    or run.domain_id != request.job_ref
                    or any(
                        run.input_ref_json.get(key) != value
                        for key, value in request.model_dump().items()
                    )
                ):
                    raise ValueError("job_score_source_identity_conflict")
                self._plan = None  # Retain the first durable route on recovery.
                return run, await self._claim_recorded_run(run)
        run = await self._kernel.start_run(
            JOB_SCORE_V1,
            input_ref={
                **request.model_dump(),
                **(
                    {
                        "runtime_route": {
                            "use_llm": self._plan.use_llm,
                            "local_method": self._plan.local_score.scoring_method
                            if self._plan.local_score
                            else "local",
                        }
                    }
                    if self._plan
                    else {}
                ),
            },
            domain_ref={"domain_type": "job_posting", "domain_id": request.job_ref},
            mode=mode.value,
            **(
                {
                    "run_id": str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"{JOB_SCORE_V1.task_id}:{JOB_SCORE_V1.version}:new:{request.event_ref}",
                        )
                    )
                }
                if mode is RuntimeMode.NEW
                else {}
            ),
        )
        return run, await self._claim_recorded_run(run)

    async def _claim_recorded_run(self, run):
        claim = await self._kernel.claim_run(
            str(run.id), self._worker_id, self._kernel.clock.now()
        )
        if claim is None and self._factory is not None:
            async with self._factory.session_factory() as session:
                attempt_id = await session.scalar(
                    select(TaskAttemptRecord.id)
                    .join(
                        WorkflowStepRecord,
                        WorkflowStepRecord.id == TaskAttemptRecord.workflow_step_id,
                    )
                    .where(
                        WorkflowStepRecord.workflow_run_id == run.id,
                        TaskAttemptRecord.status == "running",
                    )
                    .order_by(TaskAttemptRecord.attempt_number.desc())
                    .limit(1)
                )
            if attempt_id is not None:
                # Generic reclaim checks expiry, backoff, current ownership,
                # execution idempotency and a strictly newer fencing token.
                claim = await self._kernel.reclaim(
                    attempt_id, self._worker_id, self._kernel.clock.now()
                )
        if claim is None:
            raise JobScoreClaimLost("job_score_claim_unavailable")
        correlation = await self._kernel.get_claim_correlation(claim)
        if correlation.get("workflow_run_id") != str(run.id):
            raise JobScoreClaimLost("job_score_claim_run_mismatch")
        return claim

    async def score_job(
        self, request: JobScoreInput, *, mode: RuntimeMode, projection=None
    ):
        """Resolve references, execute/evaluate, and finalize the selected projection."""
        if self._factory is None:
            raise ValueError("job_score_factory_required")
        run, claim = await self.start(request, mode=mode)
        return await self._execute_claim(
            request, run, claim, mode=mode, projection=projection
        )

    async def resume(self, run_id: str, *, projection=None):
        """Resume only the recorded task/input/mode after generic reconciliation."""
        async with self._factory.session_factory() as session:
            run = await session.get(WorkflowRunRecord, run_id)
        if run is None or (
            run.workflow_definition_id,
            run.workflow_definition_version,
        ) != (JOB_SCORE_V1.task_id, JOB_SCORE_V1.version):
            raise ValueError("job_score_run_invalid")
        request = JobScoreInput.model_validate(
            {key: run.input_ref_json[key] for key in JobScoreInput.model_fields}
        )
        if run.domain_id != request.job_ref:
            raise ValueError("job_score_run_reference_mismatch")
        claim = await self._claim_recorded_run(run)
        return await self._execute_claim(
            request,
            run,
            claim,
            mode=RuntimeMode(run.runtime_mode),
            projection=projection,
        )

    async def _execute_claim(self, request, run, claim, *, mode, projection):
        started = time.perf_counter()
        heartbeat = asyncio.create_task(self._renew(claim))
        operation = RuntimeScoringOperation(
            self._factory,
            self._kernel,
            request,
            security_policy=self._security_policy,
            plan=self._plan,
            route=run.input_ref_json.get("runtime_route"),
        )
        execution_id = None
        total = ScoringUsage(model_id="none", model_version="none", provider="none")
        try:
            try:
                await operation.prepare(claim)
            except Exception as error:
                reason = (
                    error.code
                    if isinstance(error, ContextResolutionError)
                    else "job_score_context_failed"
                )
                now = self._kernel.clock.now()
                reference = f"context.{claim.id}"
                if await self._kernel.begin_execution_intent(
                    claim,
                    now=now,
                    capability_id="job.score.context",
                    capability_version=1,
                    side_effect_class="pure",
                    idempotency_class="idempotent",
                    reconciliation_reference=reference,
                ):
                    await self._kernel.persist_execution_result(
                        claim,
                        execution_role="primary",
                        capability_id="job.score.context",
                        capability_version=1,
                        side_effect_class="pure",
                        idempotency_class="idempotent",
                        reconciliation_reference=reference,
                        result_class="permanent_failure",
                        started_at=now,
                        finished_at=self._kernel.clock.now(),
                        latency_ms=max(
                            0, round((time.perf_counter() - started) * 1000)
                        ),
                        metadata={"reason_code": reason},
                    )
                    async with self._factory.session_factory() as session:
                        execution_id = await session.scalar(
                            select(ExecutionRecord.id).where(
                                ExecutionRecord.task_attempt_id == claim.task_attempt_id
                            )
                        )
                    if not await self._kernel.fail_terminal(
                        claim, reason=reason, now=self._kernel.clock.now()
                    ):
                        raise JobScoreClaimLost("job_score_runtime_claim_lost")
                    await self._trace_execution(claim, execution_id)
                else:
                    raise JobScoreClaimLost("job_score_runtime_claim_lost")
                total.reason_codes.append(reason)
                total.latency_ms = max(0, round((time.perf_counter() - started) * 1000))
                return RuntimeJobScoreResult(None, run.id, execution_id, total, reason)
            async with self._factory.session_factory() as session:
                prior_ids = set(
                    await session.scalars(
                        select(ExecutionRecord.id).where(
                            ExecutionRecord.task_attempt_id == claim.task_attempt_id
                        )
                    )
                )
            for stage in range(2):
                result = await operation.invoke(claim, local_fallback=stage == 1)
                if result.reason_code == "claim_lost":
                    raise JobScoreClaimLost("job_score_runtime_claim_lost")
                usage = operation.usage
                async with self._factory.transaction() as uow:
                    records = list(
                        await uow.session.scalars(
                            select(ExecutionRecord).where(
                                ExecutionRecord.task_attempt_id == claim.task_attempt_id
                            )
                        )
                    )
                    fresh = [record for record in records if record.id not in prior_ids]
                    if len(fresh) != 1:
                        raise RuntimeError(
                            f"job_score_execution_lineage_missing:{result.reason_code}"
                        )
                    record = fresh[0]
                    record.parent_execution_id = execution_id
                    record.execution_role = "primary" if stage == 0 else "fallback"
                    record.model_id, record.model_version, record.provider = (
                        usage.model_id,
                        usage.model_version,
                        usage.provider,
                    )
                    record.input_tokens, record.output_tokens = (
                        usage.input_tokens,
                        usage.output_tokens,
                    )
                    record.cost_usd = Decimal(usage.cost_microusd) / Decimal(1_000_000)
                    record.latency_ms = usage.latency_ms
                    record.metadata_json = {
                        **(record.metadata_json or {}),
                        "reason_codes": usage.reason_codes,
                        "model_calls": usage.model_calls,
                        "token_measurement": "estimated"
                        if usage.input_tokens
                        else "none",
                    }
                    execution_id = record.id
                    prior_ids.add(record.id)
                    if result.code is ExecutionResultCode.SUCCESS:
                        await uow.evaluations.record_validation(
                            task_attempt_id=claim.task_attempt_id,
                            execution_id=execution_id,
                            validator_id="job_score.normalization",
                            validator_version=1,
                            status="passed",
                            reason_codes_json=["job_score_valid"],
                            metrics_json={},
                        )
                    await uow.commit()
                await self._trace_execution(claim, execution_id)
                total.model_id, total.model_version, total.provider = (
                    usage.model_id,
                    usage.model_version,
                    usage.provider,
                )
                total.model_name = usage.model_name
                total.input_tokens += usage.input_tokens
                total.output_tokens += usage.output_tokens
                total.cost_microusd += usage.cost_microusd
                total.reason_codes.extend(usage.reason_codes)
                total.model_calls.extend(usage.model_calls)
                if result.code is ExecutionResultCode.SUCCESS:
                    output = result.output
                    total.latency_ms = max(
                        0, round((time.perf_counter() - started) * 1000)
                    )

                    async def project(uow):
                        if mode is RuntimeMode.NEW and projection is not None:
                            await projection(uow, output, total)

                    if not await self.complete(claim, output, projection=project):
                        raise JobScoreClaimLost("job_score_runtime_claim_lost")
                    total.latency_ms = max(
                        0, round((time.perf_counter() - started) * 1000)
                    )
                    return RuntimeJobScoreResult(
                        output,
                        run.id,
                        execution_id,
                        total,
                        "local_fallback" if stage else "success",
                    )
                if result.reason_code == "job_score_irrelevant":

                    async def acknowledge_skip(uow):
                        if mode is RuntimeMode.NEW and projection is not None:
                            await projection(uow, None, total)

                    if not await self._kernel.finalize(
                        claim,
                        {
                            "result_ref": _hash_ref("skipped"),
                            "reason_code": "job_score_irrelevant",
                        },
                        projection=acknowledge_skip,
                    ):
                        raise JobScoreClaimLost("job_score_runtime_claim_lost")
                    total.latency_ms = max(
                        0, round((time.perf_counter() - started) * 1000)
                    )
                    return RuntimeJobScoreResult(
                        None, run.id, execution_id, total, "job_score_irrelevant"
                    )
                if usage.provider == "local":
                    break
            if not await self._kernel.fail_terminal(
                claim, reason="job_score_runtime_failed", now=self._kernel.clock.now()
            ):
                raise JobScoreClaimLost("job_score_runtime_claim_lost")
            total.latency_ms = max(0, round((time.perf_counter() - started) * 1000))
            return RuntimeJobScoreResult(
                None, run.id, execution_id, total, "job_score_runtime_failed"
            )
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

    async def _trace_execution(self, claim, execution_id):
        """Correlate the durable observation without exporting content or exceptions."""
        values = await self._kernel.get_claim_correlation(claim)
        with RuntimeTelemetry().span(
            "job_score.execution_recorded",
            RuntimeCorrelation(**values, execution_id=execution_id),
        ):
            pass

    async def _renew(self, claim):
        while True:
            await asyncio.sleep(10)
            if not await self._kernel.renew_claim(claim, self._kernel.clock.now()):
                return

    async def complete(
        self,
        claim: ExecutionClaimRecord,
        result: JobScoreOutput,
        *,
        now: datetime | None = None,
        projection: Callable[[Any], Awaitable[None]] | None = None,
    ) -> bool:
        return await self._kernel.finalize(
            claim,
            {
                "result_ref": _hash_ref(result.model_dump(mode="json")),
            },
            now=now,
            projection=projection,
        )
