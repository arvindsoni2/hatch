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

import logging
import time
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.job_score import JobScore
from ..models.job import JobPosting
from ..models.cost_tracking import CostTracking
from .base_agent import BaseAgent
from .tools.event_bus import EventBus
from langchain_core.exceptions import OutputParserException
from .tools.llm_factory import get_triage_model, get_primary_model, estimate_tokens, estimate_cost
from .tools.local_scorer import score_locally, LocalScoreResult
from .tools.profile_loader import load_profile
from .tools.rate_limiter import get_limiter
from ..services import resume_store as _resume_store_module

_semantic_module = None
try:
    from .tools import semantic_scorer as _semantic_module  # type: ignore[assignment]
except ImportError:
    pass

logger = logging.getLogger("jobpilot.agent.scorer")

_BATCH_SIZE = 5
_FREE_TIER_PROVIDERS = {"google_genai", "ollama"}


class _TriageResult(BaseModel):
    relevant: bool
    reason: str = ""


class _ScoreResult(BaseModel):
    skill_match: float
    experience_match: float
    rate_match: float
    location_match: float
    overall_score: float
    reasoning: str
    keyword_matches: list[str] = []
    keyword_misses: list[str] = []
    fit_reasoning: str | None = None
    strengths: list[str] = []
    score_gaps: list[str] = []


class ScorerAgent(BaseAgent):
    """Scores pending job_discovered events against the user's profile.

    Two-tier LLM usage (both models configured in profile.yaml):
    - triage_model: fast pre-filter to skip irrelevant listings cheaply
    - primary_model: detailed 4-dimension scoring for relevant jobs

    Rate limiting is handled by the shared TokenBucketLimiter (get_limiter()).
    """

    name = "scorer"

    def __init__(self) -> None:
        super().__init__()
        self._bus = EventBus.instance()

    # ── Main entry point ──────────────────────────────────────────────

    async def run(self, db: AsyncSession, **kwargs: Any) -> dict[str, Any]:
        """Score pending job_discovered events (up to BATCH_SIZE per run)."""
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
        method = self._resolve_method(profile)
        limiter = get_limiter()

        triage_llm = get_triage_model().with_structured_output(_TriageResult)
        primary_llm = get_primary_model().with_structured_output(_ScoreResult)

        self._log.info("Scoring %d jobs using method=%s.", len(pending), method)

        if method in ("hybrid", "auto"):
            scored, skipped, errors = await self._run_hybrid(
                pending, db, profile, triage_llm, primary_llm, limiter
            )
        elif method == "local":
            scored, skipped, errors = await self._run_local_only(pending, db, profile, limiter)
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
                self._log.info("Skipping needs_enrichment job %s in hybrid scoring", job_id)
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
                "Scorer processing event=%s job_id=%s '%s' (local=%.2f, method=%s)",
                event["id"], job.id, job.title,
                local_score.overall_score,
                "llm" if id(event) in for_llm else "local",
            )
            try:
                if id(event) in for_llm:
                    result_tag = await self._score_with_llm_judge(
                        event, job, db, profile, triage_llm, primary_llm, limiter,
                        resume_text=resume_text,
                    )
                else:
                    result_tag = await self._persist_local_score(event, job, local_score, db, profile)

                await self._bus.mark_completed(event["id"], db)
                self._log.info(
                    "Scored job_id=%s: result=%s (event=%s)",
                    job.id, result_tag, event["id"],
                )
                if result_tag == "skipped":
                    skipped += 1
                else:
                    scored += 1
            except OutputParserException as exc:
                self._log.warning(
                    "LLM returned non-JSON for event %s — falling back to local score. "
                    "Raw output: %.120s",
                    event["id"], str(exc),
                )
                result_tag = await self._persist_local_score(event, job, local_score, db, profile)
                await self._bus.mark_completed(event["id"], db)
                scored += 1
            except Exception as exc:
                self._log.exception("Scoring error for event %s: %s", event["id"], exc)
                await self._bus.mark_failed(event["id"], str(exc), db)
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
                result = await db.execute(select(JobPosting).where(JobPosting.id == job_id))
                job = result.scalar_one_or_none()
                if job is None:
                    raise ValueError(f"Job {job_id} not found in DB")
                local_score = score_locally(job, profile)
                tag = await self._persist_local_score(event, job, local_score, db, profile)
                await self._bus.mark_completed(event["id"], db)
                skipped += 1 if tag == "skipped" else 0
                scored += 1 if tag != "skipped" else 0
            except Exception as exc:
                self._log.exception("Scoring error for event %s: %s", event["id"], exc)
                await self._bus.mark_failed(event["id"], str(exc), db)
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
                result = await db.execute(select(JobPosting).where(JobPosting.id == job_id))
                job = result.scalar_one_or_none()
                if job is None:
                    raise ValueError(f"Job {job_id} not found in DB")
                tag = await self._score_with_llm(
                    event, job, db, profile, triage_llm, primary_llm, limiter
                )
                await self._bus.mark_completed(event["id"], db)
                skipped += 1 if tag == "skipped" else 0
                scored += 1 if tag != "skipped" else 0
            except OutputParserException as exc:
                self._log.warning(
                    "LLM returned non-JSON for event %s — falling back to local score. "
                    "Raw output: %.120s",
                    event["id"], str(exc),
                )
                local_score = score_locally(job, profile)
                tag = await self._persist_local_score(event, job, local_score, db, profile)
                await self._bus.mark_completed(event["id"], db)
                scored += 1
            except Exception as exc:
                self._log.exception("Scoring error for event %s: %s", event["id"], exc)
                await self._bus.mark_failed(event["id"], str(exc), db)
                errors += 1
        return scored, skipped, errors

    # ── Per-job helpers ───────────────────────────────────────────────

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
        try:
            triage: _TriageResult = await triage_llm.ainvoke(triage_prompt)
        except Exception as exc:
            if "429" in str(exc) or "rate" in str(exc).lower():
                limiter.record_429()
            raise
        triage_tok_in = estimate_tokens(triage_prompt)
        triage_tok_out = estimate_tokens(triage.reason)
        db.add(CostTracking(
            agent_name="scorer",
            job_id=job_id,
            model=triage_model_name,
            tokens_in=triage_tok_in,
            tokens_out=triage_tok_out,
            cost_estimate=estimate_cost(triage_model_name, triage_tok_in, triage_tok_out),
        ))
        if not triage.relevant:
            self._log.info("Job %s pre-filtered: %s", job_id, triage.reason)
            await db.commit()
            return "skipped"

        # LLM-judge: holistic scoring with full resume + JD
        await limiter.acquire()
        scoring_prompt = self._build_llm_judge_prompt(job, profile, resume_text)
        t1 = time.monotonic()
        try:
            score: _ScoreResult = await primary_llm.ainvoke(scoring_prompt)
        except Exception as exc:
            if "429" in str(exc) or "rate" in str(exc).lower():
                limiter.record_429()
            raise
        score_ms = int((time.monotonic() - t1) * 1000)
        score_tok_in = estimate_tokens(scoring_prompt)
        score_tok_out = estimate_tokens(score.reasoning)
        cost = estimate_cost(primary_model_name, score_tok_in, score_tok_out)
        db.add(CostTracking(
            agent_name="scorer",
            job_id=job_id,
            model=primary_model_name,
            tokens_in=score_tok_in,
            tokens_out=score_tok_out,
            cost_estimate=cost,
        ))

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
        self._log.info("Job %s scored %.2f (LLM-judge) — %s", job_id, score.overall_score, score.reasoning[:80])
        return "scored"

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
        try:
            triage: _TriageResult = await triage_llm.ainvoke(triage_prompt)
        except Exception as exc:
            if "429" in str(exc) or "rate" in str(exc).lower():
                limiter.record_429()
            raise
        triage_tok_in = estimate_tokens(triage_prompt)
        triage_tok_out = estimate_tokens(triage.reason)
        db.add(CostTracking(
            agent_name="scorer",
            job_id=job_id,
            model=triage_model_name,
            tokens_in=triage_tok_in,
            tokens_out=triage_tok_out,
            cost_estimate=estimate_cost(triage_model_name, triage_tok_in, triage_tok_out),
        ))
        if not triage.relevant:
            self._log.info("Job %s pre-filtered: %s", job_id, triage.reason)
            await db.commit()
            return "skipped"

        # Detailed scoring
        await limiter.acquire()
        scoring_prompt = self._build_scoring_prompt(job, profile)
        t1 = time.monotonic()
        try:
            score: _ScoreResult = await primary_llm.ainvoke(scoring_prompt)
        except Exception as exc:
            if "429" in str(exc) or "rate" in str(exc).lower():
                limiter.record_429()
            raise
        score_ms = int((time.monotonic() - t1) * 1000)
        score_tok_in = estimate_tokens(scoring_prompt)
        score_tok_out = estimate_tokens(score.reasoning)
        cost = estimate_cost(primary_model_name, score_tok_in, score_tok_out)
        db.add(CostTracking(
            agent_name="scorer",
            job_id=job_id,
            model=primary_model_name,
            tokens_in=score_tok_in,
            tokens_out=score_tok_out,
            cost_estimate=cost,
        ))

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
        self._log.info("Job %s scored %.2f (LLM) — %s", job_id, score.overall_score, score.reasoning[:80])
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
        """Upsert a JobScore row and mark the posting as scored."""
        existing = await db.execute(select(JobScore).where(JobScore.job_id == job_id))
        row = existing.scalar_one_or_none()
        score_data = {
            "skill_match": score.skill_match,
            "experience_match": score.experience_match,
            "rate_match": score.rate_match,
            "location_match": score.location_match,
            "overall_score": score.overall_score,
            "reasoning": score.reasoning,
            "scoring_method": (m if isinstance(m := getattr(score, "scoring_method", None), str) else "llm"),
            "keyword_matches": list(v if isinstance(v := getattr(score, "keyword_matches", None), (list, tuple)) else []),
            "keyword_misses": list(v if isinstance(v := getattr(score, "keyword_misses", None), (list, tuple)) else []),
            "fit_reasoning": getattr(score, "fit_reasoning", None),
            "strengths": list(v2) if (v2 := getattr(score, "strengths", None)) and isinstance(v2, (list, tuple)) else [],
            "score_gaps": list(v3) if (v3 := getattr(score, "score_gaps", None)) and isinstance(v3, (list, tuple)) else [],
        }
        if row is None:
            db.add(JobScore(id=str(uuid.uuid4()), job_id=job_id, **score_data))
        else:
            for k, v in score_data.items():
                setattr(row, k, v)
            row.scored_at = datetime.utcnow()

        await db.execute(
            update(JobPosting).where(JobPosting.id == job_id).values(
                auto_scored=True,
                match_score=score.overall_score,
            )
        )
        await db.commit()

    # ── Strategy resolver ─────────────────────────────────────────────

    @staticmethod
    def _resolve_method(profile: Any) -> str:
        """Resolve 'auto' to a concrete method based on provider tier."""
        method = getattr(profile.scoring, "method", "auto")
        if method == "auto":
            return "hybrid" if profile.llm.provider in _FREE_TIER_PROVIDERS else "llm"
        return method

    # ── Prompt builders — all data sourced from profile.yaml ─────────

    def _build_triage_prompt(self, job: JobPosting, profile: Any) -> str:
        roles = ", ".join(profile.search.target_roles)
        locations = ", ".join(
            f"{loc.city}, {loc.country}" for loc in profile.search.locations
        )
        return (
            f"You are a job relevance filter for a {profile.candidate.title} "
            f"with {profile.candidate.years_experience} years experience.\n\n"
            f"Target roles: {roles}\n"
            f"Target locations: {locations}\n\n"
            f"Job title: {job.title}\n"
            f"Company: {job.company or 'unknown'}\n"
            f"Location: {job.location or 'unknown'}\n"
            f"Description (first 500 chars): {(job.description or '')[:500]}\n\n"
            "Is this job relevant? Reject: junior roles, unrelated domains, locations "
            "clearly outside target. Pass: anything plausibly matching the profile."
        )

    def _build_scoring_prompt(self, job: JobPosting, profile: Any) -> str:
        weights = profile.scoring.weights
        comp = profile.compensation
        primary_skills = ", ".join(profile.skills.primary)
        secondary_skills = ", ".join(profile.skills.secondary)
        preferred_domains = ", ".join(profile.domains.preferred)
        proof_summaries = "; ".join(p.summary for p in profile.proof_points)
        locations = "; ".join(
            f"{loc.city} ({loc.remote_preference})" for loc in profile.search.locations
        )

        locale_context = self._get_locale_scoring_context(profile)

        return (
            f"Score this job for a candidate with the following profile:\n\n"
            f"Title: {profile.candidate.title}, {profile.candidate.years_experience} years experience\n"
            f"Primary skills: {primary_skills}\n"
            f"Secondary skills: {secondary_skills}\n"
            f"Preferred domains: {preferred_domains}\n"
            f"Key achievements: {proof_summaries}\n"
            f"Target locations: {locations}\n"
            f"Rate range: {comp.currency} {comp.min_rate}–{comp.max_rate} ({comp.rate_type})\n\n"
            f"Job:\nTitle: {job.title}\nCompany: {job.company or 'N/A'}\n"
            f"Location: {job.location or 'N/A'}\nRate: {job.rate_text or 'N/A'}\n"
            f"Legal/contract fields: {getattr(job, 'legal_fields', None) or {'ir35_status': job.ir35_status} if job.ir35_status else {}}\n"
            f"Description:\n{(job.description or '')[:3000]}\n\n"
            f"Score on four dimensions (0.0–1.0):\n"
            f"- skill_match (weight {weights.skill_match}): how well skills match?\n"
            f"- experience_match (weight {weights.experience_match}): seniority/domain alignment?\n"
            f"- rate_match (weight {weights.rate_match}): rate within candidate range?\n"
            f"- location_match (weight {weights.location_match}): location/remote policy match?\n"
            f"{locale_context}\n"
            f"overall_score = weighted sum using the weights above.\n\n"
            f"Also return two keyword lists:\n"
            f"- keyword_matches: skills/tools mentioned in the job that the candidate clearly has (max 15)\n"
            f"- keyword_misses: skills/tools required by the job that the candidate lacks (max 10)"
        )

    def _build_llm_judge_prompt(self, job: JobPosting, profile: Any, resume_text: str) -> str:
        """Build the holistic LLM-judge prompt with full resume and JD.

        Uses resume_store.get_resume_text() for the candidate's full CV text,
        and the job's full description.  Instructs the LLM to assess semantic
        fit beyond keyword matching.
        """
        jd_text = (job.description or "")[:3000]
        weights = profile.scoring.weights
        comp = profile.compensation

        return (
            f"You are an experienced recruiter assessing candidate-job fit.\n\n"
            f"Here is a candidate's full resume:\n{resume_text}\n\n"
            f"Here is a job description:\nTitle: {job.title}\n"
            f"Company: {job.company or 'N/A'}\nLocation: {job.location or 'N/A'}\n"
            f"Rate: {job.rate_text or 'N/A'}\n\n{jd_text}\n\n"
            f"Assess fit holistically. A candidate whose title or experience maps to "
            f"the role counts as a strong match even if exact keywords differ "
            f"(e.g. 'AI Project Manager' fits 'IT Project Manager'). "
            f"Consider transferable experience, seniority, domain.\n\n"
            f"Score on four dimensions (0.0–1.0):\n"
            f"- skill_match (weight {weights.skill_match}): skills and toolset alignment\n"
            f"- experience_match (weight {weights.experience_match}): seniority/domain fit\n"
            f"- rate_match (weight {weights.rate_match}): rate within "
            f"{comp.currency} {comp.min_rate}–{comp.max_rate} ({comp.rate_type})\n"
            f"- location_match (weight {weights.location_match}): location/remote policy\n"
            f"overall_score = weighted sum.\n\n"
            f"Also return:\n"
            f"- fit_reasoning: one holistic paragraph explaining the overall fit\n"
            f"- strengths: 2-3 specific, concrete strengths this candidate brings\n"
            f"- score_gaps: genuine gaps or risks (empty list if none)\n"
            f"- keyword_matches: skills/tools the candidate clearly has (max 15)\n"
            f"- keyword_misses: required skills the candidate lacks (max 10)"
        )

    def _get_locale_scoring_context(self, profile: Any) -> str:
        try:
            from ..services.locale_service import get_scoring_context
            legal_prefs: dict[str, str] = getattr(profile.compensation, "legal_preferences", {})
            ctx = get_scoring_context(profile.locale, legal_prefs)
            if ctx:
                return f"Additional location_match guidance ({profile.locale} locale):\n{ctx}"
        except Exception:
            pass
        return ""
