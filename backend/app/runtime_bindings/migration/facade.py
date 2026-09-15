"""Compatibility facade for the Job Scoring strangler migration.

The facade deliberately owns translation and mode dispatch only.  Provider
selection, retry policy, context resolution, and evaluation remain runtime
concerns.  Shadow persistence records hashes and derived metrics only.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TypeAlias

from app.runtime import RuntimeMode
from app.runtime.storage.contracts import ShadowComparisonStore

from ..tasks.job_score import JOB_SCORE_V1, JobScoreInput, JobScoreOutput


ScoreOperation: TypeAlias = Callable[
    [JobScoreInput], Awaitable[JobScoreOutput | None] | JobScoreOutput | None
]


class JobScoreClaimLost(RuntimeError):
    """A stale runtime worker has no authority to invoke any visible writer."""


class LegacyAIRuntimeFacade:
    """Thin adapter around the legacy scorer's authoritative write path."""

    def __init__(self, score: ScoreOperation) -> None:
        self._score = score

    async def score_job(self, request: JobScoreInput) -> JobScoreOutput | None:
        result = self._score(request)
        if inspect.isawaitable(result):
            result = await result
        if result is not None and not isinstance(result, JobScoreOutput):
            raise TypeError("job score operation must return JobScoreOutput")
        return result


@dataclass(frozen=True)
class JobScoreDispatchResult:
    """Visible result and its sole writer for one already-resolved mode."""

    visible_result: JobScoreOutput | None
    authoritative_engine: str
    shadow_reason_code: str | None = None


class JobScoreMigrationDispatcher:
    """Resolve-once dispatcher with a single visible JobScore writer."""

    def __init__(
        self,
        *,
        mode: RuntimeMode,
        legacy_score: ScoreOperation,
        runtime_score: ScoreOperation,
    ) -> None:
        if not isinstance(mode, RuntimeMode):
            raise TypeError("mode must be RuntimeMode")
        self._mode = mode
        self._legacy = LegacyAIRuntimeFacade(legacy_score)
        self._runtime = runtime_score

    @property
    def mode(self) -> RuntimeMode:
        """The immutable entry-bound mode for this workflow execution."""
        return self._mode

    async def score_job(self, request: JobScoreInput) -> JobScoreDispatchResult:
        if self._mode is RuntimeMode.LEGACY:
            return JobScoreDispatchResult(
                visible_result=await self._legacy.score_job(request),
                authoritative_engine="legacy",
            )
        if self._mode is RuntimeMode.NEW:
            try:
                return JobScoreDispatchResult(
                    visible_result=await self._runtime(request),
                    authoritative_engine="runtime",
                )
            except JobScoreClaimLost:
                raise
            except Exception:
                # TaskSpec declares the existing deterministic fallback behavior.
                return JobScoreDispatchResult(
                    visible_result=await self._legacy.score_job(request),
                    authoritative_engine="legacy_fallback",
                    shadow_reason_code="runtime_failed",
                )

        legacy_result = await self._legacy.score_job(request)
        try:
            await self._runtime(request)
        except Exception:
            return JobScoreDispatchResult(
                visible_result=legacy_result,
                authoritative_engine="legacy",
                shadow_reason_code="runtime_failed",
            )
        return JobScoreDispatchResult(
            visible_result=legacy_result,
            authoritative_engine="legacy",
        )


def _metadata_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"


def _shortlist(score: JobScoreOutput, threshold: float = 0.75) -> bool:
    return score.overall_score >= threshold


async def record_job_score_shadow_comparison(
    store: ShadowComparisonStore,
    *,
    request: JobScoreInput,
    legacy_result: JobScoreOutput,
    runtime_result: JobScoreOutput | None,
    runtime_execution_id: str | None = None,
    legacy_execution_ref: str | None = None,
    latency_ms: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_microusd: int = 0,
    model_id: str = "unknown",
    model_version: str = "unknown",
    provider: str = "unknown",
    runtime_run_id: str | None = None,
    reason_code: str = "success",
    reason_codes: list[str] | None = None,
    threshold: float = 0.75,
    model_calls: list[dict[str, object]] | None = None,
    created_at: datetime | None = None,
) -> object:
    """Store a bounded SHADOW comparison without retaining score content.

    The shared store enforces the 30-day maximum and rejects content-bearing
    metrics at its persistence boundary.
    """
    delta = (
        None
        if runtime_result is None
        else round(abs(runtime_result.overall_score - legacy_result.overall_score), 4)
    )
    agreement = (
        None
        if runtime_result is None
        else _shortlist(legacy_result, threshold)
        == _shortlist(runtime_result, threshold)
    )
    return await store.record(
        slice_name="job_score",
        domain_type="job_posting",
        domain_id_hash=_metadata_hash({"job_ref": request.job_ref}),
        legacy_execution_ref=legacy_execution_ref,
        runtime_execution_id=runtime_execution_id,
        legacy_result_hash=_metadata_hash(legacy_result.model_dump(mode="json")),
        runtime_result_hash=_metadata_hash(
            runtime_result.model_dump(mode="json")
            if runtime_result
            else {"reason_code": reason_code}
        ),
        comparison_status="runtime_failed"
        if runtime_result is None
        else "same"
        if delta == 0
        else "different",
        metrics_json={
            "score_delta": delta,
            "shortlist_agreement": agreement,
            "task_version": JOB_SCORE_V1.version,
            "latency_ms": max(0, int(latency_ms)),
            "input_tokens": max(0, int(input_tokens)),
            "output_tokens": max(0, int(output_tokens)),
            "cost_microusd": max(0, int(cost_microusd)),
            "reason_code": reason_code
            if runtime_result is None or reason_code != "success"
            else "same"
            if delta == 0
            else "score_delta",
            "reason_codes": reason_codes or [],
            "model_id": model_id,
            "model_version": model_version,
            "provider": provider,
            "runtime_run_id": runtime_run_id,
            "token_measurement": "estimated" if input_tokens else "none",
            "model_calls": model_calls or [],
        },
        created_at=created_at,
    )
