"""Durable workflow adapter for one Job Scoring runtime execution."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from app.runtime.workflow import ExecutionClaimRecord, WorkflowKernel

from ..tasks.job_score import JOB_SCORE_V1, JobScoreInput, JobScoreOutput


def _hash_ref(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


class DurableJobScoreRuntime:
    """Binds Job Scoring to the generic fenced workflow kernel.

    It persists opaque references and output hashes only. Product code owns the
    visible JobScore projection; this adapter owns durable runtime lifecycle.
    """

    def __init__(self, kernel: WorkflowKernel, *, worker_id: str) -> None:
        self._kernel = kernel
        self._worker_id = worker_id

    async def start(self, request: JobScoreInput):
        run = await self._kernel.start_run(
            JOB_SCORE_V1,
            input_ref={
                "job_ref_hash": _hash_ref(request.job_ref),
                "profile_ref_hash": _hash_ref(request.profile_ref),
                "event_ref_hash": _hash_ref(request.event_ref),
            },
            domain_ref={"domain_type": "job_posting", "domain_id": request.job_ref},
            mode="new",
        )
        claim = await self._kernel.claim_next(self._worker_id, self._kernel.clock.now())
        if claim is None:
            raise RuntimeError("job_score_claim_unavailable")
        return run, claim

    async def complete(
        self,
        claim: ExecutionClaimRecord,
        result: JobScoreOutput,
        *,
        now: datetime | None = None,
    ) -> bool:
        return await self._kernel.finalize(
            claim,
            {
                "result_ref": _hash_ref(result.model_dump(mode="json")),
                "job_ref_hash": _hash_ref("job_score"),
            },
            now=now,
        )
