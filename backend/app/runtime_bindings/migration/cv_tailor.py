"""CV Tailoring strangler migration with evaluation-only SHADOW execution."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.runtime import RuntimeMode
from app.runtime.contracts import ExecutionResultCode
from app.runtime.execution.adapters import ArtifactCapabilityAdapter
from app.runtime.execution.models import CapabilityInvocationContext
from app.runtime_bindings.capabilities import ArtifactRenderInput, ArtifactRenderOutput

from ..tasks.cv_tailor import (
    CVTailorInput,
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


class CVTailorRuntime:
    """Run deterministic checks before bounded repair/fallback and artifact commit."""

    def __init__(
        self,
        *,
        produce: TailorOperation,
        repair: TailorOperation | None = None,
        fallback: TailorOperation | None = None,
        commit_artifact: ArtifactCommitter | None = None,
    ) -> None:
        self._produce = produce
        self._repair = repair
        self._fallback = fallback
        self._commit_artifact = commit_artifact

    async def run(
        self, request: CVTailorInput, *, mode: RuntimeMode
    ) -> CVTailorRuntimeResult:
        if not isinstance(mode, RuntimeMode):
            raise TypeError("mode must be RuntimeMode")
        produced = await _await(self._produce(request))
        if isinstance(produced, ExecutionResultCode):
            return CVTailorRuntimeResult(produced, "cv_tailor_producer_failed")
        output = produced
        validation = validate_cv_tailor_output(output)
        repairs = 0
        if (
            validation.code is not ExecutionResultCode.SUCCESS
            and self._repair is not None
        ):
            repairs = 1
            repaired = await _await(self._repair(request))
            if not isinstance(repaired, ExecutionResultCode):
                output = repaired
                validation = validate_cv_tailor_output(output)
        fallback_used = False
        if (
            validation.code is not ExecutionResultCode.SUCCESS
            and self._fallback is not None
        ):
            fallback = await _await(self._fallback(request))
            if not isinstance(fallback, ExecutionResultCode):
                output = fallback
                validation = validate_cv_tailor_output(output)
                fallback_used = validation.code is ExecutionResultCode.SUCCESS
        if validation.code is not ExecutionResultCode.SUCCESS:
            return CVTailorRuntimeResult(
                validation.code, validation.reason_code, repair_count=repairs
            )
        # SHADOW has no visible writer. It returns evaluation-only output and
        # never constructs or invokes the committing artifact adapter.
        if mode is not RuntimeMode.NEW:
            return CVTailorRuntimeResult(
                ExecutionResultCode.SUCCESS,
                "cv_tailor_fallback" if fallback_used else "cv_tailor_valid",
                output=output,
                repair_count=repairs,
            )
        if self._commit_artifact is None:
            return CVTailorRuntimeResult(
                ExecutionResultCode.PERMANENT_FAILURE,
                "cv_tailor_artifact_unavailable",
                repair_count=repairs,
            )
        try:
            artifact_ref = await self._commit_via_artifact_adapter(request, output)
        except Exception:
            return CVTailorRuntimeResult(
                ExecutionResultCode.PERMANENT_FAILURE,
                "cv_tailor_artifact_failed",
                repair_count=repairs,
            )
        return CVTailorRuntimeResult(
            ExecutionResultCode.SUCCESS,
            "cv_tailor_fallback" if fallback_used else "cv_tailor_valid",
            output=output,
            artifact_ref=artifact_ref,
            repair_count=repairs,
        )

    async def _commit_via_artifact_adapter(
        self, request: CVTailorInput, output: CVTailorOutput
    ) -> str:
        async def handler(_, __):
            artifact_ref = await _await(self._commit_artifact(output))
            return ArtifactRenderOutput(
                artifact_ref=artifact_ref,
                byte_count=output.artifact_bytes,
            )

        adapter = ArtifactCapabilityAdapter(handler)
        result = await adapter.invoke(
            ArtifactRenderInput(
                source_ref="cv-tailor:validated",
                application_ref=request.application_ref,
                idempotency_key=f"cv-tailor:{request.application_ref}:{request.variant}",
            ),
            CapabilityInvocationContext(
                deadline=None,
                budgets=None,
                idempotency_key=f"cv-tailor:{request.application_ref}:{request.variant}",
                correlation_handle="cv-tailor-artifact",
                data_egress=False,
                allowed_models=None,
                allowed_providers=None,
                model_id=None,
                provider=None,
            ),
        )
        return result.output.artifact_ref


@dataclass(frozen=True)
class CVTailorDispatchResult:
    visible_result: CVTailorOutput | None
    authoritative_engine: str
    shadow_reason_code: str | None = None
    runtime_code: ExecutionResultCode | None = None


class CVTailorMigrationDispatcher:
    """Resolve-once dispatcher: SHADOW evaluates but cannot visibly write."""

    def __init__(
        self,
        *,
        mode: RuntimeMode,
        legacy_generate: TailorOperation,
        runtime_generate: TailorOperation,
    ) -> None:
        if not isinstance(mode, RuntimeMode):
            raise TypeError("mode must be RuntimeMode")
        self._mode = mode
        self._legacy = legacy_generate
        self._runtime = runtime_generate

    @property
    def mode(self) -> RuntimeMode:
        return self._mode

    async def generate(self, request: CVTailorInput) -> CVTailorDispatchResult:
        if self._mode is RuntimeMode.LEGACY:
            return CVTailorDispatchResult(await _await(self._legacy(request)), "legacy")
        if self._mode is RuntimeMode.NEW:
            runtime = await _await(self._runtime(request))
            if isinstance(runtime, ExecutionResultCode):
                return CVTailorDispatchResult(None, "runtime", runtime_code=runtime)
            return CVTailorDispatchResult(runtime, "runtime")
        legacy = await _await(self._legacy(request))
        try:
            await _await(self._runtime(request))
        except Exception:
            return CVTailorDispatchResult(
                legacy, "legacy", shadow_reason_code="runtime_failed"
            )
        return CVTailorDispatchResult(legacy, "legacy")
