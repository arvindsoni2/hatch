"""Runtime-owned context, routing, execution and evaluation for job.score."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any


from app.agents.tools import llm_factory, profile_loader
from app.agents.tools.local_scorer import score_locally
from app.agents.tools.scoring_contract import ScoringPrompts
from app.models.job import JobPosting
from app.runtime.context import ContextItem, ContextRegistry, ContextResolver
from app.runtime.context.resolver import ContextResolutionError
from app.runtime.evaluation.service import EvaluationService
from app.runtime.evaluation.validators import EvaluationFinding
from app.runtime.intelligence import (
    ModelDescriptor,
    ModelRegistry,
    ModelRouter,
    RoutingPreference,
)
from app.runtime.control import ConstraintSet, ControlPlane
from app.runtime.execution import (
    CapabilityDescriptor,
    CapabilityRegistry,
    CapabilityResult,
    ExecutionGateway,
    IdempotencyClass,
    SideEffectClass,
)
from app.runtime.contracts import ExecutionResultCode
from app.runtime.execution.adapters.native import NativeCapabilityAdapter
from app.runtime.observability import RuntimeCorrelation
from app.services import resume_store

from ..tasks.job_score import JOB_SCORE_V1, JobScoreInput, JobScoreOutput


def score_output(score: Any) -> JobScoreOutput:
    """Translate shared scoring mathematics into the immutable output schema."""
    return JobScoreOutput(
        **{
            name: float(getattr(score, name))
            for name in (
                "skill_match",
                "experience_match",
                "rate_match",
                "location_match",
                "overall_score",
            )
        },
        reasoning=str(getattr(score, "reasoning", "")),
        keyword_matches=tuple(getattr(score, "keyword_matches", ()) or ()),
        keyword_misses=tuple(getattr(score, "keyword_misses", ()) or ()),
        fit_reasoning=getattr(score, "fit_reasoning", None),
        strengths=tuple(getattr(score, "strengths", ()) or ()),
        score_gaps=tuple(getattr(score, "score_gaps", ()) or ()),
        scoring_method=getattr(score, "scoring_method", "llm"),
    )


@dataclass
class ScoringUsage:
    model_id: str = "local-keyword"
    model_name: str = "local-keyword"
    model_version: str = "1"
    provider: str = "local"
    input_tokens: int = 0
    output_tokens: int = 0
    cost_microusd: int = 0
    latency_ms: int = 0
    reason_codes: list[str] = field(default_factory=list)
    model_calls: list[dict[str, object]] = field(default_factory=list)


class JobScoreContextSource:
    """Reads the referenced product sources once, retaining content only in memory."""

    provider_id = "job.score.sources"
    capabilities = tuple(item.capability for item in JOB_SCORE_V1.context_requirements)

    def __init__(self, factory, request: JobScoreInput):
        self.factory = factory
        self.request = request
        self.job = None
        self.profile = None
        self.resume = ""

    async def load(self):
        if (
            self.request.profile_ref != "profile:current"
            or not self.request.job_ref.startswith("job:")
        ):
            raise ValueError("context_reference_unknown")
        async with self.factory.session_factory() as session:
            self.job = await session.get(
                JobPosting, self.request.job_ref.removeprefix("job:")
            )
        if self.job is None:
            raise ValueError("context_job_missing")
        self.profile = profile_loader.load_profile().model_copy(deep=True)
        try:
            self.resume = resume_store.get_resume_text()
        except Exception:
            self.resume = ""

    async def resolve(self, task_attempt_id, requirement):
        capability = requirement.capability
        if capability == "candidate.profile_summary":
            value, source_ref = (
                self.profile.model_dump(mode="json"),
                self.request.profile_ref,
            )
        elif capability == "candidate.resume_text":
            value, source_ref = self.resume, "resume:current"
        elif capability == "job.description":
            value, source_ref = self.job.description, self.request.job_ref
        else:
            value, source_ref = (
                {
                    field: getattr(self.job, field)
                    for field in (
                        "title",
                        "location",
                        "rate_text",
                        "rate_min",
                        "rate_max",
                        "currency",
                    )
                },
                self.request.job_ref,
            )
        if not value:
            return None
        encoded = json.dumps(value, sort_keys=True, default=str)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        return ContextItem(
            capability=capability,
            provider_id=self.provider_id,
            source_ref=source_ref,
            descriptor=capability.replace(".", "-"),
            summary=None,
            provenance={"source_version": digest},
            freshness=None,
            sensitivity="confidential",
            token_estimate=min(8192, max(1, len(encoded) // 4)),
            confidence=1.0,
            content_hash=digest,
        )


class ScoringInvocation(JobScoreInput):
    model_id: str
    provider: str


@dataclass(frozen=True)
class RuntimeScoringPlan:
    source: JobScoreContextSource
    local_score: JobScoreOutput | None
    use_llm: bool
    deferred: bool = False


def _runtime_pre_score(source):
    if source.resume:
        try:
            from app.agents.tools import semantic_scorer
        except ImportError:
            pass
        else:
            score = semantic_scorer.score_semantic(
                source.job, source.profile, source.resume
            )
            return None if score.deferred else score_output(score)
    return score_output(score_locally(source.job, source.profile))


async def prepare_job_score_batch(factory, requests):
    """Independently reproduce hybrid top-fraction/borderline selection by reference."""
    prepared = []
    plans = {}
    for request in requests:
        source = JobScoreContextSource(factory, request)
        try:
            await source.load()
        except Exception:
            continue  # Per-run context resolution records the safe failure.
        if source.job.needs_enrichment:
            plans[request.event_ref] = RuntimeScoringPlan(
                source, None, False, deferred=True
            )
            continue
        score = _runtime_pre_score(source)
        if score is None:
            plans[request.event_ref] = RuntimeScoringPlan(
                source, None, False, deferred=True
            )
        else:
            prepared.append((source, score))
    prepared.sort(key=lambda item: item[1].overall_score, reverse=True)
    for rank, (source, score) in enumerate(prepared):
        config = source.profile.scoring
        top_count = max(1, round(len(prepared) * config.hybrid_llm_top_pct))
        band = getattr(config, "hybrid_llm_band", 0.15)
        use_llm = (
            rank < top_count
            or abs(score.overall_score - config.shortlist_threshold) <= band
        )
        plans[source.request.event_ref] = RuntimeScoringPlan(source, score, use_llm)
    return plans


class RuntimeScoringOperation:
    """Owns declared context and finite execution policy; never writes JobScore."""

    def __init__(
        self, factory, kernel, request, *, security_policy=None, plan=None, route=None
    ):
        self.factory, self.kernel, self.request = factory, kernel, request
        self.source = (
            plan.source if plan is not None else JobScoreContextSource(factory, request)
        )
        self.plan = plan
        self.route = route
        self.usage = ScoringUsage()
        self.registry = None
        self.policy = None
        self.security_policy = security_policy
        self.invoked = False

    async def prepare(self, claim):
        self.correlation = RuntimeCorrelation(
            **await self.kernel.get_claim_correlation(claim)
        )
        if self.source.job is None:
            await self.source.load()
        contexts = ContextRegistry()
        contexts.register(self.source)
        resolver = ContextResolver(self.factory, contexts)
        attempt = await self.kernel.get_attempt(claim.task_attempt_id)
        if attempt.context_package_id:
            package = await resolver.load(attempt.context_package_id)
            if package is None:
                raise ContextResolutionError("context_package_missing")
            expected = {item.capability: item for item in package.items}
            for requirement in JOB_SCORE_V1.context_requirements:
                current = await self.source.resolve(claim.task_attempt_id, requirement)
                previous = expected.get(requirement.capability)
                if current != previous:
                    raise ContextResolutionError("context_source_changed")
        else:
            await resolver.resolve(
                claim.task_attempt_id, JOB_SCORE_V1.context_requirements, budget=32768
            )
        profile = self.source.profile
        self.local_model_id = (
            "local-semantic"
            if (
                self.plan is not None
                and self.plan.local_score is not None
                and self.plan.local_score.scoring_method == "semantic"
            )
            or (self.route and self.route.get("local_method") == "semantic")
            else "local-keyword"
        )
        local = ModelDescriptor(
            model_id=self.local_model_id,
            version="1",
            provider="local",
            model_name=self.local_model_id,
            local_or_cloud="local",
            privacy_characteristics="local",
        )
        models = [local]
        if profile.scoring.method != "local":
            cfg = profile.llm
            for role, name in (
                ("configured-primary", cfg.primary_model),
                ("configured-triage", cfg.triage_model),
            ):
                models.append(
                    ModelDescriptor(
                        model_id=role,
                        version="config."
                        + hashlib.sha256(
                            f"{cfg.provider}|{name}|{cfg.reasoning}".encode()
                        ).hexdigest()[:24],
                        provider=cfg.provider,
                        model_name=name,
                        local_or_cloud="local"
                        if cfg.provider in {"ollama", "llamacpp"}
                        else "cloud",
                        privacy_characteristics="local"
                        if cfg.provider in {"ollama", "llamacpp"}
                        else "provider_configured",
                    )
                )
        self.registry = ModelRegistry(models)
        self.policy = ControlPlane(model_registry=self.registry).evaluate(
            task_spec=JOB_SCORE_V1,
            system=ConstraintSet(allowed_capabilities=frozenset({"job.score.compute"})),
            security_policy=self.security_policy,
        )
        async with self.factory.transaction() as uow:
            await uow.evaluations.record_policy_decision(
                task_attempt_id=claim.task_attempt_id,
                policy_id="job.score.policy",
                policy_version=1,
                decision=self.policy.decision,
                reason_code="job_score_declared_policy",
            )
            await uow.commit()

    async def invoke(self, claim, *, local_fallback=False):
        self.usage = ScoringUsage()
        use_llm = (
            self.plan.use_llm
            if self.plan
            else self.route.get("use_llm", True)
            if self.route
            else True
        )
        model_id = (
            self.local_model_id
            if local_fallback
            or not use_llm
            or self.source.profile.scoring.method == "local"
            else "configured-primary"
        )
        router = ModelRouter(self.registry)
        decision = router.route(
            JOB_SCORE_V1, self.policy, RoutingPreference.force(model_id)
        )
        async with self.factory.transaction() as uow:
            await router.persist_decision(
                uow.evaluations,
                task_attempt_id=claim.task_attempt_id,
                capability_id="job.score.compute",
                decision=decision,
            )
            await uow.commit()
        model = decision.selected_descriptor
        if model is None:
            rejected = self.registry.get(model_id)
            self.usage.model_id, self.usage.model_version, self.usage.provider = (
                rejected.model_id,
                rejected.version,
                rejected.provider,
            )
            return await self._record_refusal(claim, "job_score_model_excluded")
        self.usage.model_id, self.usage.model_version, self.usage.provider = (
            model.model_id,
            model.version,
            model.provider,
        )
        self.usage.model_name = model.model_name
        if model.provider != "local":
            triage = router.route(
                JOB_SCORE_V1, self.policy, RoutingPreference.force("configured-triage")
            )
            async with self.factory.transaction() as uow:
                await router.persist_decision(
                    uow.evaluations,
                    task_attempt_id=claim.task_attempt_id,
                    capability_id="job.score.compute",
                    decision=triage,
                )
                await uow.commit()
            if triage.selected_descriptor is None:
                return await self._record_refusal(claim, "job_score_triage_excluded")
        capabilities = CapabilityRegistry()
        capabilities.register(
            CapabilityDescriptor(
                capability_id="job.score.compute",
                version=1,
                input_model=ScoringInvocation,
                output_model=JobScoreOutput,
                side_effect_class=SideEffectClass.PURE
                if model.provider == "local"
                else SideEffectClass.READ_ONLY_EXTERNAL,
                idempotency_class=IdempotencyClass.IDEMPOTENT,
                default_timeout_seconds=720.0,
                uses_model_routing=True,
                uses_provider_routing=True,
                requires_data_egress=model.local_or_cloud == "cloud",
            ),
            NativeCapabilityAdapter(self.compute),
        )
        started = time.perf_counter()
        self.invoked = False
        result = await ExecutionGateway(
            registry=capabilities, kernel=self.kernel, model_registry=self.registry
        ).invoke(
            claim,
            capability_id="job.score.compute",
            payload={
                **self.request.model_dump(),
                "model_id": model.model_id,
                "provider": model.provider,
            },
            policy=self.policy,
            selection_proof=decision.selection_proof,
        )
        self.usage.latency_ms = max(0, round((time.perf_counter() - started) * 1000))
        if result.code is ExecutionResultCode.POLICY_DENIED and not self.invoked:
            return await self._record_refusal(claim, result.reason_code)
        self.usage.reason_codes.append(result.reason_code)
        return result

    async def _record_refusal(self, claim, reason):
        """Persist a fenced metadata-only observation for pre-invocation refusals."""
        now = self.kernel.clock.now()
        reference = f"policy.{claim.id}.{self.usage.model_id}"
        owned = await self.kernel.begin_execution_intent(
            claim,
            now=now,
            capability_id="job.score.compute",
            capability_version=1,
            side_effect_class="pure",
            idempotency_class="idempotent",
            reconciliation_reference=reference,
        )
        if not owned:
            return CapabilityResult(
                code=ExecutionResultCode.PERMANENT_FAILURE, reason_code="claim_lost"
            )
        persisted = await self.kernel.persist_execution_result(
            claim,
            execution_role="primary",
            capability_id="job.score.compute",
            capability_version=1,
            side_effect_class="pure",
            idempotency_class="idempotent",
            reconciliation_reference=reference,
            result_class="policy_denied",
            started_at=now,
            finished_at=self.kernel.clock.now(),
            latency_ms=self.usage.latency_ms,
            metadata={"reason_code": reason},
        )
        self.usage.reason_codes.append(reason)
        return CapabilityResult(
            code=ExecutionResultCode.POLICY_DENIED,
            reason_code=reason if persisted else "claim_lost",
        )

    async def compute(self, payload, context):
        self.invoked = True
        # Prompt construction and deterministic normalization are shared with the
        # legacy scorer. No legacy execution, persistence or fallback is invoked.
        from app.agents.tools.scoring_contract import (
            _ScoreResult,
            _TriageResult,
            _normalise_score_result,
        )
        from app.runtime.execution import CapabilityResult
        from app.runtime.contracts import ExecutionResultCode
        from app.agents.tools.rate_limiter import get_limiter

        profile, job = self.source.profile, self.source.job
        if payload.provider == "local":
            output = self.plan.local_score if self.plan is not None else None
            if output is None:
                output = (
                    _runtime_pre_score(self.source)
                    if payload.model_id == "local-semantic"
                    else score_output(score_locally(job, profile))
                )
        else:
            prompts = ScoringPrompts()
            limiter = get_limiter()

            async def generate(role, prompt, schema):
                model = self.registry.get(role)
                await limiter.acquire()
                started = time.perf_counter()
                tok_in = llm_factory.estimate_tokens(prompt)
                self.usage.input_tokens += tok_in
                call = {
                    "model_id": model.model_id,
                    "model_name": model.model_name,
                    "model_version": model.version,
                    "provider": model.provider,
                    "input_tokens": tok_in,
                    "output_tokens": 0,
                    "cost_microusd": 0,
                    "latency_ms": 0,
                    "reason_code": "model_failed",
                }
                self.usage.model_calls.append(call)
                try:
                    config = profile.llm
                    if role == "configured-triage" and config.triage_base_url:
                        config = config.model_copy(
                            update={"base_url": config.triage_base_url}
                        )
                    client = llm_factory._build_model(model.model_name, config)
                    # Schema mode is bound to the resolved profile snapshot too.
                    structured = client.with_structured_output(
                        schema,
                        **(
                            {"method": "json_schema"}
                            if config.provider == "llamacpp"
                            else {}
                        ),
                    )
                    response = await structured.ainvoke(prompt)
                except Exception:
                    call["cost_microusd"] = round(
                        llm_factory.estimate_cost(model.model_name, tok_in, 0)
                        * 1_000_000
                    )
                    self.usage.cost_microusd += call["cost_microusd"]
                    raise
                finally:
                    call["latency_ms"] = max(
                        0, round((time.perf_counter() - started) * 1000)
                    )
                tok_out = llm_factory.estimate_tokens(response.model_dump_json())
                call["output_tokens"] = tok_out
                call["reason_code"] = "success"
                call["cost_microusd"] = round(
                    llm_factory.estimate_cost(model.model_name, tok_in, tok_out)
                    * 1_000_000
                )
                self.usage.output_tokens += tok_out
                self.usage.cost_microusd += call["cost_microusd"]
                return response

            triage = await generate(
                "configured-triage",
                prompts._build_triage_prompt(job, profile),
                _TriageResult,
            )
            if not triage.relevant:
                return CapabilityResult(
                    code=ExecutionResultCode.PERMANENT_FAILURE,
                    reason_code="job_score_irrelevant",
                )
            method = prompts._resolve_method(profile)
            prompt = (
                prompts._build_llm_judge_prompt(job, profile, self.source.resume)
                if method == "hybrid"
                else prompts._build_scoring_prompt(job, profile)
            )
            score = await generate("configured-primary", prompt, _ScoreResult)
            output = score_output(
                _normalise_score_result(
                    score,
                    profile.scoring.weights,
                    candidate_text=self.source.resume
                    if method == "hybrid"
                    else prompts._profile_evidence_text(profile),
                    job_text=prompts._job_evidence_text(job),
                )
            )

        def validate(subject):
            JobScoreOutput.model_validate(subject)
            total = round(
                sum(
                    getattr(subject, key) * getattr(profile.scoring.weights, key)
                    for key in (
                        "skill_match",
                        "experience_match",
                        "rate_match",
                        "location_match",
                    )
                ),
                4,
            )
            if abs(total - subject.overall_score) > 0.001:
                return EvaluationFinding.failed(
                    "job_score_normalization_failed", terminal=True
                )
            return EvaluationFinding.passed("job_score_valid")

        evaluation = await EvaluationService(
            deterministic_validators=(validate,)
        ).evaluate(
            output,
            policy=JOB_SCORE_V1.evaluation_policy,
            constraints=self.policy.effective_constraints,
            correlation=self.correlation,
        )
        self.usage.reason_codes.extend(evaluation.reason_codes)
        if evaluation.status != "passed":
            return CapabilityResult(
                code=ExecutionResultCode.VALIDATION_FAILURE,
                reason_code="job_score_validation_failed",
            )
        return CapabilityResult.success(output)
