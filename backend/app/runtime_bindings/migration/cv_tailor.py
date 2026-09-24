"""CV Tailoring strangler migration with evaluation-only SHADOW execution."""

from __future__ import annotations

import hashlib
import inspect
import json
import uuid
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass

from app.runtime import RuntimeMode
from app.runtime.contracts import ExecutionResultCode
from app.runtime.execution.adapters import ArtifactCapabilityAdapter
from app.runtime_bindings.capabilities import ArtifactRenderInput, ArtifactRenderOutput
from app.runtime.context import ContextRegistry, ContextResolver
from app.runtime.control import ConstraintSet, ControlPlane
from app.runtime.execution import (
    CapabilityDescriptor,
    CapabilityRegistry,
    ExecutionGateway,
    IdempotencyClass,
    SideEffectClass,
)
from app.runtime.execution.adapters.native import NativeCapabilityAdapter
from app.runtime.intelligence import ModelDescriptor, ModelRegistry, ModelRouter, RoutingPreference
from app.runtime_bindings.context import (
    JobPostingContextProvider,
    ProfileYamlContextProvider,
    ResumeContextProvider,
)
from app.runtime_bindings.context.models import ContextSourceMetadata

from ..tasks.cv_tailor import (
    CV_TAILOR_V1,
    CVTailorInput,
    CVTailorInvocation,
    CVTailorOutput,
    validate_cv_tailor_output,
)


TailorOperation = Callable[
    [CVTailorInput],
    CVTailorOutput
    | ExecutionResultCode
    | Awaitable[CVTailorOutput | ExecutionResultCode],
]
ArtifactCommitter = Callable[[CVTailorOutput], str | Awaitable[str]]


async def _await(value):
    return await value if inspect.isawaitable(value) else value


@dataclass(frozen=True)
class CVTailorRuntimeResult:
    code: ExecutionResultCode
    reason_code: str
    output: CVTailorOutput | None = None
    artifact_ref: str | None = None
    repair_count: int = 0


class DurableCVTailorRuntime:
    """Generic-kernel execution for one CV Tailoring attempt.

    Candidate/JD content is deliberately retained only by the product callbacks;
    the runtime persists opaque references, hashes and stable reason codes.
    """

    def __init__(
        self,
        kernel,
        *,
        factory,
        worker_id: str,
        produce: TailorOperation,
        source_claims: Iterable[str],
        job_description: str,
        repair: TailorOperation | None = None,
        fallback: TailorOperation | None = None,
        commit_artifact: ArtifactCommitter | None = None,
    ) -> None:
        self._kernel = kernel
        self._factory = factory
        self._worker_id = worker_id
        self._produce = produce
        self._source_claims = tuple(source_claims)
        self._job_description = job_description
        self._repair = repair
        self._fallback = fallback
        self._commit_artifact = commit_artifact

    async def run(
        self, request: CVTailorInput, *, mode: RuntimeMode
    ) -> CVTailorRuntimeResult:
        run = await self._kernel.start_run(
            CV_TAILOR_V1,
            input_ref=request.model_dump(),
            domain_ref={"domain_type": "application", "domain_id": request.application_ref},
            mode=mode.value,
            run_id=str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"cv.tailor:1:{mode.value}:{request.request_ref}",
                )
            ),
        )
        claim = await self._kernel.claim_run(
            str(run.id), self._worker_id, self._kernel.clock.now()
        )
        if claim is None:
            return CVTailorRuntimeResult(
                ExecutionResultCode.PERMANENT_FAILURE, "cv_tailor_claim_unavailable"
            )
        try:
            await self._resolve_context(claim.task_attempt_id, request)
        except Exception:
            await self._kernel.fail_terminal(
                claim, reason="cv_tailor_context_failed", now=self._kernel.clock.now()
            )
            return CVTailorRuntimeResult(
                ExecutionResultCode.PERMANENT_FAILURE, "cv_tailor_context_failed"
            )
        policy = ControlPlane().evaluate(
            task_spec=CV_TAILOR_V1,
            system=ConstraintSet(
                allowed_capabilities=frozenset(
                    {"cv.tailor.generate", "artifact.render_cv"}
                )
            ),
        )
        async with self._factory.transaction() as uow:
            await uow.evaluations.record_policy_decision(
                task_attempt_id=claim.task_attempt_id,
                policy_id="cv.tailor.policy",
                policy_version=1,
                decision=policy.decision,
                reason_code="cv_tailor_declared_policy",
            )
            await uow.commit()
        # This is a real router decision and an immutable proof passed to the
        # gateway.  A local descriptor is intentionally used only when no
        # configured catalog is available (offline/system tests).
        try:
            model_registry = ModelRegistry.from_configured_models()
        except Exception:
            model_registry = ModelRegistry((
                ModelDescriptor(
                    model_id="cv-tailor-local", version="1", provider="local",
                    model_name="cv-tailor-product-callback", local_or_cloud="local",
                    quality_score=1.0, base_rank=1.0,
                ),
            ))
        routing = ModelRouter(model_registry).route(
            CV_TAILOR_V1, policy, RoutingPreference.auto()
        )
        async with self._factory.transaction() as uow:
            await ModelRouter(model_registry).persist_decision(
                uow.evaluations,
                task_attempt_id=claim.task_attempt_id,
                capability_id="cv.tailor.generate",
                decision=routing,
            )
            await uow.commit()
        if routing.selected_descriptor is None:
            await self._kernel.fail_terminal(
                claim, reason="cv_tailor_model_unavailable", now=self._kernel.clock.now()
            )
            return CVTailorRuntimeResult(
                ExecutionResultCode.POLICY_DENIED, "cv_tailor_model_unavailable"
            )
        registry = CapabilityRegistry()

        async def generate(payload, _context):
            return await _await(self._produce(payload))

        registry.register(
            CapabilityDescriptor(
                capability_id="cv.tailor.generate",
                version=1,
                input_model=CVTailorInvocation,
                output_model=CVTailorOutput,
                side_effect_class=SideEffectClass.READ_ONLY_EXTERNAL,
                idempotency_class=IdempotencyClass.IDEMPOTENT,
                requires_data_egress=(
                    routing.selected_descriptor.local_or_cloud == "cloud"
                ),
                uses_model_routing=True,
                uses_provider_routing=True,
            ),
            NativeCapabilityAdapter(generate),
        )
        gateway = ExecutionGateway(
            registry=registry, kernel=self._kernel, model_registry=model_registry
        )
        generated = await gateway.invoke(
            claim,
            capability_id="cv.tailor.generate",
            payload={
                **request.model_dump(),
                "model_id": routing.selected_descriptor.model_id,
                "provider": routing.selected_descriptor.provider,
            },
            policy=policy,
            selection_proof=routing.selection_proof,
        )
        if generated.code is not ExecutionResultCode.SUCCESS:
            await self._kernel.fail_terminal(
                claim, reason=generated.reason_code, now=self._kernel.clock.now()
            )
            return CVTailorRuntimeResult(generated.code, generated.reason_code)
        output = generated.output
        validation = validate_cv_tailor_output(output, source_claims=self._source_claims)
        repairs = 0
        if validation.code is not ExecutionResultCode.SUCCESS and self._repair is not None:
            repairs = 1
            repaired = await _await(self._repair(request))
            if not isinstance(repaired, ExecutionResultCode):
                output = repaired
                validation = validate_cv_tailor_output(output, source_claims=self._source_claims)
        fallback_used = False
        if validation.code is not ExecutionResultCode.SUCCESS and self._fallback is not None:
            fallback = await _await(self._fallback(request))
            if not isinstance(fallback, ExecutionResultCode):
                output = fallback
                validation = validate_cv_tailor_output(output, source_claims=self._source_claims)
                fallback_used = validation.code is ExecutionResultCode.SUCCESS
        async with self._factory.transaction() as uow:
            await uow.evaluations.record_validation(
                task_attempt_id=claim.task_attempt_id,
                validator_id="cv_tailor.source_supported_claims",
                validator_version=1,
                status="passed" if validation.code is ExecutionResultCode.SUCCESS else "failed",
                reason_codes_json=[validation.reason_code],
                metrics_json={},
            )
            await uow.commit()
        if validation.code is not ExecutionResultCode.SUCCESS:
            await self._kernel.fail_terminal(
                claim, reason=validation.reason_code, now=self._kernel.clock.now()
            )
            return CVTailorRuntimeResult(validation.code, validation.reason_code, repair_count=repairs)
        if mode is RuntimeMode.SHADOW:
            await self._kernel.finalize(
                claim, {"result_ref": _hash_output(output)}, now=self._kernel.clock.now()
            )
            return CVTailorRuntimeResult(
                ExecutionResultCode.SUCCESS,
                "cv_tailor_fallback" if fallback_used else "cv_tailor_valid",
                output=output,
                repair_count=repairs,
            )
        if self._commit_artifact is None:
            await self._kernel.fail_terminal(
                claim, reason="cv_tailor_artifact_unavailable", now=self._kernel.clock.now()
            )
            return CVTailorRuntimeResult(
                ExecutionResultCode.PERMANENT_FAILURE, "cv_tailor_artifact_unavailable"
            )
        async def render_artifact(_, __):
            artifact_ref = await _await(self._commit_artifact(output))
            return ArtifactRenderOutput(artifact_ref=artifact_ref, byte_count=output.artifact_bytes)

        registry.register(
            CapabilityDescriptor(
                capability_id="artifact.render_cv",
                version=1,
                input_model=ArtifactRenderInput,
                output_model=ArtifactRenderOutput,
                side_effect_class=SideEffectClass.ARTIFACT_GENERATION,
                idempotency_class=IdempotencyClass.IDEMPOTENT_WITH_KEY,
                default_timeout_seconds=60.0,
            ),
            ArtifactCapabilityAdapter(render_artifact),
        )
        artifact_result = await ExecutionGateway(registry=registry, kernel=self._kernel).invoke(
            claim,
            capability_id="artifact.render_cv",
            payload={
                "source_ref": "cv-tailor:validated",
                "application_ref": request.application_ref,
                "idempotency_key": f"cv-tailor:{claim.task_attempt_id}",
            },
            policy=policy,
        )
        if artifact_result.code is not ExecutionResultCode.SUCCESS:
            await self._kernel.fail_terminal(
                claim, reason=artifact_result.reason_code, now=self._kernel.clock.now()
            )
            return CVTailorRuntimeResult(
                artifact_result.code, artifact_result.reason_code, repair_count=repairs
            )
        artifact = artifact_result.output.artifact_ref
        await self._kernel.finalize(
            claim,
            {"result_ref": _hash_output(output)},
            now=self._kernel.clock.now(),
        )
        return CVTailorRuntimeResult(
            ExecutionResultCode.SUCCESS,
            "cv_tailor_fallback" if fallback_used else "cv_tailor_valid",
            output=output,
            artifact_ref=artifact,
            repair_count=repairs,
        )

    async def _resolve_context(self, attempt_id: str, request: CVTailorInput) -> None:
        async def job_source(_, capability: str):
            text = self._job_description
            digest = hashlib.sha256(text.encode()).hexdigest()
            return ContextSourceMetadata(
                source_ref=request.job_ref,
                descriptor=capability.replace(".", "-"),
                provenance={"source_version": digest},
                freshness=None,
                sensitivity="confidential",
                token_estimate=min(8192, max(1, len(text) // 4)),
                confidence=1.0,
                content_hash=digest,
            )

        registry = ContextRegistry()
        registry.register(ProfileYamlContextProvider())
        registry.register(ResumeContextProvider())
        registry.register(JobPostingContextProvider(job_source))
        await ContextResolver(self._factory, registry).resolve(
            attempt_id,
            CV_TAILOR_V1.context_requirements,
            budget=32768,
        )


def _hash_output(output: CVTailorOutput) -> str:
    # Runtime records must be metadata-only: do not hash a dumped CV payload
    # here because model dumps are frequently captured by observability hooks.
    encoded = json.dumps(
        {
            "artifact_ref": output.artifact_ref,
            "artifact_bytes": output.artifact_bytes,
            "experience_count": len(output.tailored_cv.experience),
            "achievement_count": sum(
                len(item.achievements) for item in output.tailored_cv.experience
            ),
            "skill_group_count": len(output.tailored_cv.skills),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()
