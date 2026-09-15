"""Scorer Sub-Agent — LLM-based job fit scoring driven by profile.yaml.

Supports four scoring strategies (profile.scoring.method):
  auto    — hybrid if provider is free-tier, llm otherwise
  llm     — full LLM scoring for every relevant job (original behaviour)
  local   — keyword scoring only, no LLM calls beyond triage
  hybrid  — local score all, send top hybrid_llm_top_pct% to LLM for refinement

All scoring weights, target roles, compensation range, skills, and location
preferences are read from the user's profile.yaml at runtime via profile_loader.
The LLM used is determined by profile.yaml llm config via llm_factory.
"""

from __future__ import annotations

import asyncio
import logging
import json
import time
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.job_score import JobScore
from ..models.job import JobPosting
from ..models.cost_tracking import CostTracking
from ..models.agent_event import AgentEvent
from ..observability import get_telemetry, trace_workflow
from ..runtime import RuntimeMode, resolve_runtime_mode
from ..runtime.storage.sqlite import SQLiteRuntimeUnitOfWorkFactory
from ..runtime.workflow import WorkflowKernel
from ..runtime_bindings.migration import (
    DurableJobScoreRuntime,
    JobScoreMigrationDispatcher,
    record_job_score_shadow_comparison,
)
from ..runtime_bindings.tasks import JobScoreInput
from ..runtime_bindings.migration.scoring import score_output, prepare_job_score_batch
from ..database import AsyncSessionLocal
from .base_agent import BaseAgent
from .tools.event_bus import EventBus
from langchain_core.exceptions import OutputParserException
from .tools.llm_factory import (
    get_triage_model,
    get_primary_model,
    with_schema,
    estimate_tokens,
    estimate_cost,
)
from .tools.local_scorer import score_locally, LocalScoreResult
from .tools.profile_loader import load_profile
from .tools.rate_limiter import get_limiter
from ..services import resume_store as _resume_store_module
from .tools.scoring_contract import (
    ScoringPrompts,
    _ScoreResult,
    _TriageResult,
    _normalise_score_result,
)

_semantic_module = None
try:
    from .tools import semantic_scorer as _semantic_module  # type: ignore[assignment]
except ImportError:
    pass

logger = logging.getLogger("jobpilot.agent.scorer")

_BATCH_SIZE = 5
_JOB_SCORE_MODE: ContextVar[RuntimeMode] = ContextVar(
    "job_score_mode", default=RuntimeMode.LEGACY
)
_JOB_SCORE_PLANS: ContextVar[dict] = ContextVar("job_score_plans", default={})


class ScorerAgent(ScoringPrompts, BaseAgent):
    """Scores pending job_discovered events against the user's profile.

    Two-tier LLM usage (both models configured in profile.yaml):
    - triage_model: fast pre-filter to skip irrelevant listings cheaply
    - primary_model: detailed 4-dimension scoring for relevant jobs

    Rate limiting is handled by the shared TokenBucketLimiter (get_limiter()).
    """

    name = "scorer"

    def __init__(self, *, runtime_factory=None) -> None:
        super().__init__()
        self._bus = EventBus.instance()
        self._runtime_factory = runtime_factory or SQLiteRuntimeUnitOfWorkFactory(
            AsyncSessionLocal
        )

    # ── Main entry point ──────────────────────────────────────────────

    async def run(self, db: AsyncSession, **kwargs: Any) -> dict[str, Any]:
        """Score pending job_discovered events (up to BATCH_SIZE per run)."""
        # Bind the slice mode before any polling or scoring work so a running
        # batch cannot switch engines if configuration changes mid-execution.
        runtime_mode = resolve_runtime_mode("job_score")
        self._log.info("Job Scoring runtime mode bound to %s.", runtime_mode.value)
        mode_token = _JOB_SCORE_MODE.set(runtime_mode)
        plans_token = _JOB_SCORE_PLANS.set({})
        try:
            return await self._run_bound(db, **kwargs)
        finally:
            _JOB_SCORE_MODE.reset(mode_token)
            _JOB_SCORE_PLANS.reset(plans_token)

    async def _run_bound(self, db: AsyncSession, **kwargs: Any) -> dict[str, Any]:
        """Execute a batch under the mode already bound at its entry boundary."""
        await self.update_state(db, "running", {"task": "scoring pending jobs"})

        pending = await self._bus.poll(
            db, event_type="job_discovered", status="pending", limit=_BATCH_SIZE
        )

        if not pending:
            self._log.info("No pending job_discovered events.")
            await self.update_state(db, "idle")
            return {"scored": 0, "skipped": 0, "errors": 0}

        self._log.info(
            "Scorer processing %d job_discovered event(s) (event_ids=%s).",
            len(pending),
            [e["id"] for e in pending],
        )

        profile = load_profile()
        if (
            _JOB_SCORE_MODE.get() is not RuntimeMode.LEGACY
            and self._resolve_method(profile) == "hybrid"
        ):
            _JOB_SCORE_PLANS.set(
                await prepare_job_score_batch(
                    self._runtime_factory,
                    [
                        JobScoreInput(
                            job_ref=f"job:{event['payload']['job_id']}",
                            profile_ref="profile:current",
                            event_ref=f"event:{event['id']}",
                        )
                        for event in pending
                    ],
                )
            )
        if _JOB_SCORE_MODE.get() is RuntimeMode.NEW:
            scored, skipped, errors = await self._run_runtime_only(pending, db, profile)
            await self.update_state(db, "idle")
            return {"scored": scored, "skipped": skipped, "errors": errors}
        method = self._resolve_method(profile)
        limiter = get_limiter()

        triage_llm = (
            with_schema(get_triage_model(), _TriageResult)
            if method != "local"
            else None
        )
        primary_llm = (
            with_schema(get_primary_model(), _ScoreResult)
            if method != "local"
            else None
        )

        self._log.info("Scoring %d jobs using method=%s.", len(pending), method)

        if method in ("hybrid", "auto"):
            scored, skipped, errors = await self._run_hybrid(
                pending, db, profile, triage_llm, primary_llm, limiter
            )
        elif method == "local":
            scored, skipped, errors = await self._run_local_only(
                pending, db, profile, limiter
            )
        else:  # llm
            scored, skipped, errors = await self._run_llm_only(
                pending, db, profile, triage_llm, primary_llm, limiter
            )

        await self.update_state(db, "idle")
        self._log.info(
            "Scoring run: %d scored, %d skipped, %d errors.", scored, skipped, errors
        )
        return {"scored": scored, "skipped": skipped, "errors": errors}

    # ── Strategy implementations ──────────────────────────────────────

    async def _run_runtime_only(self, pending, db, profile):
        scored = skipped = errors = 0
        for event in pending:
            plan = _JOB_SCORE_PLANS.get().get(f"event:{event['id']}")
            if plan is not None and plan.deferred:
                continue
            await self._bus.mark_processing(event["id"], db)
            try:

                async def fallback():
                    job = await db.get(JobPosting, event["payload"]["job_id"])
                    return await self._persist_local_score(
                        event, job, score_locally(job, profile), db, profile
                    )

                tag = await self._dispatch_event(event, db, fallback, profile)
                await self._bus.mark_completed(event["id"], db)
                skipped += tag == "skipped"
                scored += tag != "skipped"
            except Exception:
                await db.rollback()
                await self._bus.mark_failed(event["id"], "job_score_runtime_failed", db)
                errors += 1
        return scored, skipped, errors

    async def _dispatch_event(self, event, db, legacy_operation, profile):
        mode = _JOB_SCORE_MODE.get()
        job_id = event["payload"]["job_id"]
        request = JobScoreInput(
            job_ref=f"job:{job_id}",
            profile_ref="profile:current",
            event_ref=f"event:{event['id']}",
        )
        legacy_output = None

        async def legacy_score(_):
            nonlocal legacy_output
            tag = await legacy_operation()
            if tag == "skipped":
                return None
            row = await db.scalar(select(JobScore).where(JobScore.job_id == job_id))
            legacy_output = score_output(row)
            return legacy_output

        async def runtime_score(_):
            runtime = DurableJobScoreRuntime(
                WorkflowKernel(self._runtime_factory),
                worker_id=f"scorer-{uuid.uuid4()}",
                factory=self._runtime_factory,
                plan=_JOB_SCORE_PLANS.get().get(request.event_ref),
            )

            async def project(uow, output, usage):
                await self._write_visible_score(
                    job_id, output, uow.session, commit=False
                )
                for call in usage.model_calls:
                    uow.session.add(
                        CostTracking(
                            agent_name="scorer",
                            job_id=job_id,
                            model=call["model_name"],
                            tokens_in=call["input_tokens"],
                            tokens_out=call["output_tokens"],
                            cost_estimate=call["cost_microusd"] / 1_000_000,
                        )
                    )
                payload = {
                    "job_id": job_id,
                    "score": output.overall_score,
                    **output.model_dump(mode="json", exclude={"overall_score"}),
                    "model_used": usage.model_name,
                    "tokens_in": usage.input_tokens,
                    "tokens_out": usage.output_tokens,
                    "cost_estimate": usage.cost_microusd / 1_000_000,
                    "duration_ms": usage.latency_ms,
                }
                await uow.session.execute(
                    sqlite_insert(AgentEvent)
                    .values(
                        id=str(
                            uuid.uuid5(
                                uuid.NAMESPACE_URL, request.event_ref + ":job_scored"
                            )
                        ),
                        event_type="job_scored",
                        source_agent="scorer",
                        payload=json.dumps(payload),
                        status="pending",
                    )
                    .on_conflict_do_nothing(index_elements=["id"])
                )

            observed = await runtime.score_job(request, mode=mode, projection=project)
            if mode is RuntimeMode.SHADOW and legacy_output is not None:
                try:
                    async with self._runtime_factory.transaction() as uow:
                        await record_job_score_shadow_comparison(
                            uow.shadow,
                            request=request,
                            legacy_result=legacy_output,
                            runtime_result=observed.output,
                            runtime_execution_id=observed.execution_id,
                            legacy_execution_ref=request.event_ref,
                            latency_ms=observed.usage.latency_ms,
                            input_tokens=observed.usage.input_tokens,
                            output_tokens=observed.usage.output_tokens,
                            cost_microusd=observed.usage.cost_microusd,
                            model_id=observed.usage.model_id,
                            model_version=observed.usage.model_version,
                            provider=observed.usage.provider,
                            runtime_run_id=observed.run_id,
                            reason_code=observed.reason_code,
                            reason_codes=observed.usage.reason_codes,
                            threshold=profile.scoring.shortlist_threshold,
                            model_calls=observed.usage.model_calls,
                        )
                        await uow.commit()
                except Exception:
                    self._log.warning(
                        "Job scoring shadow persistence failed: shadow_store_unavailable"
                    )
            if (
                observed.output is None
                and observed.reason_code != "job_score_irrelevant"
            ):
                raise RuntimeError("job_score_runtime_failed")
            return observed.output

        result = await JobScoreMigrationDispatcher(
            mode=mode, legacy_score=legacy_score, runtime_score=runtime_score
        ).score_job(request)
        return "skipped" if result.visible_result is None else "scored"

    async def _run_hybrid(
        self,
        pending: list[dict],
        db: AsyncSession,
        profile: Any,
        triage_llm: Any,
        primary_llm: Any,
        limiter: Any,
    ) -> tuple[int, int, int]:
        """Semantic-score all jobs, then send top N% + borderline to LLM-judge."""
        top_pct = getattr(profile.scoring, "hybrid_llm_top_pct", 0.20)
        scored = skipped = errors = 0

        # Get resume text once (used for both semantic scoring and LLM prompt)
        try:
            resume_text = _resume_store_module.get_resume_text()
        except Exception:
            resume_text = ""

        # Phase 1 — semantic pre-score (no LLM calls)
        # Skip jobs that need enrichment first
        local_results: list[tuple[dict, Any | None, LocalScoreResult]] = []
        for event in pending:
            payload = event["payload"]
            job_id = payload["job_id"]
            result = await db.execute(select(JobPosting).where(JobPosting.id == job_id))
            job = result.scalar_one_or_none()
            if job is None:
                continue

            # Skip jobs that need enrichment (no useful JD yet)
            if getattr(job, "needs_enrichment", False):
                self._log.info(
                    "Skipping needs_enrichment job %s in hybrid scoring", job_id
                )
                continue

            if _semantic_module is not None and resume_text:
                sem_score = _semantic_module.score_semantic(job, profile, resume_text)
                if sem_score.deferred:
                    # Treat deferred as needs_enrichment — skip for now
                    continue
                # Wrap SemanticScoreResult as a LocalScoreResult-compatible object
                # so Phase 2 selection logic works uniformly
                local_score = LocalScoreResult(
                    skill_match=sem_score.skill_match or 0.0,
                    experience_match=sem_score.experience_match or 0.0,
                    rate_match=sem_score.rate_match or 0.0,
                    location_match=sem_score.location_match or 0.0,
                    overall_score=sem_score.overall_score or 0.0,
                    keyword_matches=sem_score.keyword_matches,
                    keyword_misses=sem_score.keyword_misses,
                    reasoning=sem_score.reasoning,
                    scoring_method="semantic",
                )
            else:
                local_score = score_locally(job, profile)

            local_results.append((event, job, local_score))

        if not local_results:
            return 0, 0, 0

        # Phase 2 — determine which jobs get LLM refinement
        # Strategy: send borderline jobs (within ±llm_band of threshold) to LLM,
        # plus always include the top top_pct.  Skip clearly-low jobs (< threshold-band).
        threshold = getattr(profile.scoring, "shortlist_threshold", 0.75)
        llm_band = getattr(profile.scoring, "hybrid_llm_band", 0.15)
        band_low = threshold - llm_band
        band_high = threshold + llm_band

        local_results.sort(key=lambda x: x[2].overall_score, reverse=True)
        llm_count = max(1, round(len(local_results) * top_pct))

        for_llm: set[int] = set()
        for i, (event, job, ls) in enumerate(local_results):
            in_top_n = i < llm_count
            in_band = band_low <= ls.overall_score <= band_high
            if in_top_n or in_band:
                for_llm.add(id(event))

        # Phase 3 — process each job
        for event, job, local_score in local_results:
            await self._bus.mark_processing(event["id"], db)
            self._log.info(
                "Scorer processing event=%s job_id=%s (local=%.2f, method=%s)",
                event["id"],
                job.id,
                local_score.overall_score,
                "llm" if id(event) in for_llm else "local",
            )
            try:

                async def legacy_operation():
                    if id(event) in for_llm:
                        try:
                            return await self._score_with_llm_judge(
                                event,
                                job,
                                db,
                                profile,
                                triage_llm,
                                primary_llm,
                                limiter,
                                resume_text=resume_text,
                            )
                        except (OutputParserException, TimeoutError):
                            pass
                    return await self._persist_local_score(
                        event, job, local_score, db, profile
                    )

                result_tag = await self._dispatch_event(
                    event, db, legacy_operation, profile
                )

                await self._bus.mark_completed(event["id"], db)
                self._log.info(
                    "Scored job_id=%s: result=%s (event=%s)",
                    job.id,
                    result_tag,
                    event["id"],
                )
                if result_tag == "skipped":
                    skipped += 1
                else:
                    scored += 1
            except OutputParserException:
                self._log.warning(
                    "LLM structured output failed for event %s; using local fallback.",
                    event["id"],
                )
                result_tag = await self._persist_local_score(
                    event, job, local_score, db, profile
                )
                await self._bus.mark_completed(event["id"], db)
                scored += 1
            except TimeoutError:
                self._log.warning(
                    "LLM call timed out for event %s — falling back to local score.",
                    event["id"],
                )
                result_tag = await self._persist_local_score(
                    event, job, local_score, db, profile
                )
                await self._bus.mark_completed(event["id"], db)
                scored += 1
            except Exception:
                self._log.warning(
                    "Scoring error for event %s: job_score_failed", event["id"]
                )
                await self._bus.mark_failed(event["id"], "job_score_failed", db)
                errors += 1

        return scored, skipped, errors

    async def _run_local_only(
        self,
        pending: list[dict],
        db: AsyncSession,
        profile: Any,
        limiter: Any,
    ) -> tuple[int, int, int]:
        """Score all jobs using keyword matching — no LLM beyond triage."""
        scored = skipped = errors = 0
        for event in pending:
            await self._bus.mark_processing(event["id"], db)
            try:
                payload = event["payload"]
                job_id = payload["job_id"]
                result = await db.execute(
                    select(JobPosting).where(JobPosting.id == job_id)
                )
                job = result.scalar_one_or_none()
                if job is None:
                    raise ValueError(f"Job {job_id} not found in DB")

                async def legacy_operation():
                    local_score = score_locally(job, profile)
                    return await self._persist_local_score(
                        event, job, local_score, db, profile
                    )

                tag = await self._dispatch_event(event, db, legacy_operation, profile)
                await self._bus.mark_completed(event["id"], db)
                skipped += 1 if tag == "skipped" else 0
                scored += 1 if tag != "skipped" else 0
            except Exception:
                self._log.warning(
                    "Scoring error for event %s: job_score_failed", event["id"]
                )
                await self._bus.mark_failed(event["id"], "job_score_failed", db)
                errors += 1
        return scored, skipped, errors

    async def _run_llm_only(
        self,
        pending: list[dict],
        db: AsyncSession,
        profile: Any,
        triage_llm: Any,
        primary_llm: Any,
        limiter: Any,
    ) -> tuple[int, int, int]:
        """Original full-LLM strategy: triage + detailed scoring for every job."""
        scored = skipped = errors = 0
        for event in pending:
            await self._bus.mark_processing(event["id"], db)
            try:
                payload = event["payload"]
                job_id = payload["job_id"]
                result = await db.execute(
                    select(JobPosting).where(JobPosting.id == job_id)
                )
                job = result.scalar_one_or_none()
                if job is None:
                    raise ValueError(f"Job {job_id} not found in DB")

                async def legacy_operation():
                    try:
                        return await self._score_with_llm(
                            event, job, db, profile, triage_llm, primary_llm, limiter
                        )
                    except (OutputParserException, TimeoutError):
                        return await self._persist_local_score(
                            event, job, score_locally(job, profile), db, profile
                        )

                tag = await self._dispatch_event(event, db, legacy_operation, profile)
                await self._bus.mark_completed(event["id"], db)
                skipped += 1 if tag == "skipped" else 0
                scored += 1 if tag != "skipped" else 0
            except OutputParserException:
                self._log.warning(
                    "LLM structured output failed for event %s; using local fallback.",
                    event["id"],
                )
                local_score = score_locally(job, profile)
                tag = await self._persist_local_score(
                    event, job, local_score, db, profile
                )
                await self._bus.mark_completed(event["id"], db)
                scored += 1
            except TimeoutError:
                self._log.warning(
                    "LLM call timed out for event %s — falling back to local score.",
                    event["id"],
                )
                local_score = score_locally(job, profile)
                tag = await self._persist_local_score(
                    event, job, local_score, db, profile
                )
                await self._bus.mark_completed(event["id"], db)
                scored += 1
            except Exception:
                self._log.warning(
                    "Scoring error for event %s: job_score_failed", event["id"]
                )
                await self._bus.mark_failed(event["id"], "job_score_failed", db)
                errors += 1
        return scored, skipped, errors

    # ── Per-job helpers ───────────────────────────────────────────────

    @trace_workflow("job_scoring")
    async def _score_with_llm_judge(
        self,
        event: dict[str, Any],
        job: JobPosting,
        db: AsyncSession,
        profile: Any,
        triage_llm: Any,
        primary_llm: Any,
        limiter: Any,
        resume_text: str = "",
    ) -> str:
        """Run triage + LLM-judge scoring for a single job using full resume and JD."""
        job_id = job.id
        profile_cfg = profile.llm
        triage_model_name = profile_cfg.triage_model
        primary_model_name = profile_cfg.primary_model

        # Triage pre-filter
        await limiter.acquire()
        triage_prompt = self._build_triage_prompt(job, profile)
        triage_started = time.monotonic()
        try:
            triage: _TriageResult = await asyncio.wait_for(
                triage_llm.ainvoke(triage_prompt), timeout=120
            )
        except Exception as exc:
            get_telemetry().record_model_call(
                workflow="job_scoring",
                provider=str(getattr(profile_cfg, "provider", "configured")),
                model_id=str(triage_model_name),
                duration_ms=(time.monotonic() - triage_started) * 1000,
                input_tokens=estimate_tokens(triage_prompt),
                outcome="failed",
            )
            if "429" in str(exc) or "rate" in str(exc).lower():
                limiter.record_429()
            raise
        triage_tok_in = estimate_tokens(triage_prompt)
        triage_tok_out = estimate_tokens(triage.reason)
        get_telemetry().record_model_call(
            workflow="job_scoring",
            provider=str(getattr(profile_cfg, "provider", "configured")),
            model_id=str(triage_model_name),
            duration_ms=(time.monotonic() - triage_started) * 1000,
            input_tokens=triage_tok_in,
            output_tokens=triage_tok_out,
        )
        db.add(
            CostTracking(
                agent_name="scorer",
                job_id=job_id,
                model=triage_model_name,
                tokens_in=triage_tok_in,
                tokens_out=triage_tok_out,
                cost_estimate=estimate_cost(
                    triage_model_name, triage_tok_in, triage_tok_out
                ),
            )
        )
        if not triage.relevant:
            self._log.info("Job %s pre-filtered.", job_id)
            await db.commit()
            return "skipped"

        # LLM-judge: holistic scoring with full resume + JD
        await limiter.acquire()
        scoring_prompt = self._build_llm_judge_prompt(job, profile, resume_text)
        t1 = time.monotonic()
        try:
            score: _ScoreResult = await asyncio.wait_for(
                primary_llm.ainvoke(scoring_prompt), timeout=600
            )
        except Exception as exc:
            get_telemetry().record_model_call(
                workflow="job_scoring",
                provider=str(getattr(profile_cfg, "provider", "configured")),
                model_id=str(primary_model_name),
                duration_ms=(time.monotonic() - t1) * 1000,
                input_tokens=estimate_tokens(scoring_prompt),
                outcome="failed",
            )
            if "429" in str(exc) or "rate" in str(exc).lower():
                limiter.record_429()
            raise
        score = _normalise_score_result(
            score,
            profile.scoring.weights,
            candidate_text=resume_text,
            job_text=self._job_evidence_text(job),
        )
        score_ms = int((time.monotonic() - t1) * 1000)
        score_tok_in = estimate_tokens(scoring_prompt)
        score_tok_out = estimate_tokens(score.reasoning)
        get_telemetry().record_model_call(
            workflow="job_scoring",
            provider=str(getattr(profile_cfg, "provider", "configured")),
            model_id=str(primary_model_name),
            duration_ms=score_ms,
            input_tokens=score_tok_in,
            output_tokens=score_tok_out,
        )
        cost = estimate_cost(primary_model_name, score_tok_in, score_tok_out)
        db.add(
            CostTracking(
                agent_name="scorer",
                job_id=job_id,
                model=primary_model_name,
                tokens_in=score_tok_in,
                tokens_out=score_tok_out,
                cost_estimate=cost,
            )
        )

        await self._persist_score(job_id, score, db)
        await self.emit_event(
            "job_scored",
            {
                "job_id": job_id,
                "score": score.overall_score,
                "skill_match": score.skill_match,
                "experience_match": score.experience_match,
                "rate_match": score.rate_match,
                "location_match": score.location_match,
                "reasoning": score.reasoning,
                "keyword_matches": score.keyword_matches,
                "keyword_misses": score.keyword_misses,
                "model_used": primary_model_name,
                "tokens_in": score_tok_in,
                "tokens_out": score_tok_out,
                "cost_estimate": cost,
                "duration_ms": score_ms,
                "scoring_method": "llm",
            },
            db,
        )
        self._log.info("Job %s scored %.2f (LLM-judge).", job_id, score.overall_score)
        return "scored"

    @trace_workflow("job_scoring")
    async def _score_with_llm(
        self,
        event: dict[str, Any],
        job: JobPosting,
        db: AsyncSession,
        profile: Any,
        triage_llm: Any,
        primary_llm: Any,
        limiter: Any,
    ) -> str:
        """Run triage + LLM scoring for a single job, respecting rate limits."""
        job_id = job.id
        profile_cfg = profile.llm
        triage_model_name = profile_cfg.triage_model
        primary_model_name = profile_cfg.primary_model

        # Triage pre-filter
        await limiter.acquire()
        triage_prompt = self._build_triage_prompt(job, profile)
        triage_started = time.monotonic()
        try:
            triage: _TriageResult = await asyncio.wait_for(
                triage_llm.ainvoke(triage_prompt), timeout=120
            )
        except Exception as exc:
            get_telemetry().record_model_call(
                workflow="job_scoring",
                provider=str(getattr(profile_cfg, "provider", "configured")),
                model_id=str(triage_model_name),
                duration_ms=(time.monotonic() - triage_started) * 1000,
                input_tokens=estimate_tokens(triage_prompt),
                outcome="failed",
            )
            if "429" in str(exc) or "rate" in str(exc).lower():
                limiter.record_429()
            raise
        triage_tok_in = estimate_tokens(triage_prompt)
        triage_tok_out = estimate_tokens(triage.reason)
        get_telemetry().record_model_call(
            workflow="job_scoring",
            provider=str(getattr(profile_cfg, "provider", "configured")),
            model_id=str(triage_model_name),
            duration_ms=(time.monotonic() - triage_started) * 1000,
            input_tokens=triage_tok_in,
            output_tokens=triage_tok_out,
        )
        db.add(
            CostTracking(
                agent_name="scorer",
                job_id=job_id,
                model=triage_model_name,
                tokens_in=triage_tok_in,
                tokens_out=triage_tok_out,
                cost_estimate=estimate_cost(
                    triage_model_name, triage_tok_in, triage_tok_out
                ),
            )
        )
        if not triage.relevant:
            self._log.info("Job %s pre-filtered.", job_id)
            await db.commit()
            return "skipped"

        # Detailed scoring
        await limiter.acquire()
        scoring_prompt = self._build_scoring_prompt(job, profile)
        t1 = time.monotonic()
        try:
            score: _ScoreResult = await asyncio.wait_for(
                primary_llm.ainvoke(scoring_prompt), timeout=600
            )
        except Exception as exc:
            get_telemetry().record_model_call(
                workflow="job_scoring",
                provider=str(getattr(profile_cfg, "provider", "configured")),
                model_id=str(primary_model_name),
                duration_ms=(time.monotonic() - t1) * 1000,
                input_tokens=estimate_tokens(scoring_prompt),
                outcome="failed",
            )
            if "429" in str(exc) or "rate" in str(exc).lower():
                limiter.record_429()
            raise
        score = _normalise_score_result(
            score,
            profile.scoring.weights,
            candidate_text=self._profile_evidence_text(profile),
            job_text=self._job_evidence_text(job),
        )
        score_ms = int((time.monotonic() - t1) * 1000)
        score_tok_in = estimate_tokens(scoring_prompt)
        score_tok_out = estimate_tokens(score.reasoning)
        get_telemetry().record_model_call(
            workflow="job_scoring",
            provider=str(getattr(profile_cfg, "provider", "configured")),
            model_id=str(primary_model_name),
            duration_ms=score_ms,
            input_tokens=score_tok_in,
            output_tokens=score_tok_out,
        )
        cost = estimate_cost(primary_model_name, score_tok_in, score_tok_out)
        db.add(
            CostTracking(
                agent_name="scorer",
                job_id=job_id,
                model=primary_model_name,
                tokens_in=score_tok_in,
                tokens_out=score_tok_out,
                cost_estimate=cost,
            )
        )

        await self._persist_score(job_id, score, db)
        await self.emit_event(
            "job_scored",
            {
                "job_id": job_id,
                "score": score.overall_score,
                "skill_match": score.skill_match,
                "experience_match": score.experience_match,
                "rate_match": score.rate_match,
                "location_match": score.location_match,
                "reasoning": score.reasoning,
                "keyword_matches": score.keyword_matches,
                "keyword_misses": score.keyword_misses,
                "model_used": primary_model_name,
                "tokens_in": score_tok_in,
                "tokens_out": score_tok_out,
                "cost_estimate": cost,
                "duration_ms": score_ms,
                "scoring_method": "llm",
            },
            db,
        )
        self._log.info("Job %s scored %.2f (LLM).", job_id, score.overall_score)
        return "scored"

    async def _persist_local_score(
        self,
        event: dict[str, Any],
        job: JobPosting,
        local: LocalScoreResult,
        db: AsyncSession,
        profile: Any,
    ) -> str:
        job_id = job.id
        await self._persist_score(job_id, local, db)
        await self.emit_event(
            "job_scored",
            {
                "job_id": job_id,
                "score": local.overall_score,
                "skill_match": local.skill_match,
                "experience_match": local.experience_match,
                "rate_match": local.rate_match,
                "location_match": local.location_match,
                "reasoning": local.reasoning,
                "keyword_matches": local.keyword_matches,
                "keyword_misses": local.keyword_misses,
                "model_used": "local-keyword",
                "tokens_in": 0,
                "tokens_out": 0,
                "cost_estimate": 0.0,
                "duration_ms": 0,
                "scoring_method": "local",
            },
            db,
        )
        self._log.info("Job %s scored %.2f (local).", job_id, local.overall_score)
        return "scored"

    async def _persist_score(self, job_id: str, score: Any, db: AsyncSession) -> None:
        """Legacy projection; execution dispatch happens before this helper."""
        await self._write_visible_score(job_id, score, db)

    async def _write_visible_score(
        self, job_id: str, score: Any, db: AsyncSession, *, commit: bool = True
    ) -> None:
        """The sole JobScore projection writer selected by the dispatcher."""
        score_data = {
            "skill_match": score.skill_match,
            "experience_match": score.experience_match,
            "rate_match": score.rate_match,
            "location_match": score.location_match,
            "overall_score": score.overall_score,
            "reasoning": score.reasoning,
            "scoring_method": (
                m
                if isinstance(m := getattr(score, "scoring_method", None), str)
                else "llm"
            ),
            "keyword_matches": list(
                v
                if isinstance(
                    v := getattr(score, "keyword_matches", None), (list, tuple)
                )
                else []
            ),
            "keyword_misses": list(
                v
                if isinstance(
                    v := getattr(score, "keyword_misses", None), (list, tuple)
                )
                else []
            ),
            "fit_reasoning": getattr(score, "fit_reasoning", None),
            "strengths": list(v2)
            if (v2 := getattr(score, "strengths", None))
            and isinstance(v2, (list, tuple))
            else [],
            "score_gaps": list(v3)
            if (v3 := getattr(score, "score_gaps", None))
            and isinstance(v3, (list, tuple))
            else [],
        }
        await db.execute(
            sqlite_insert(JobScore)
            .values(id=str(uuid.uuid4()), job_id=job_id, **score_data)
            .on_conflict_do_update(
                index_elements=["job_id"],
                set_={**score_data, "scored_at": datetime.utcnow()},
            )
        )

        await db.execute(
            update(JobPosting)
            .where(JobPosting.id == job_id)
            .values(
                auto_scored=True,
                match_score=score.overall_score,
            )
        )
        if commit:
            await db.commit()
