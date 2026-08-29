"""Policy-gated capability invocation with fenced durable persistence."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from ..contracts import ExecutionResultCode
from ..control import PolicyDecision
from ..workflow import (
    ApprovalManager,
    ExecutionClaimRecord,
    WorkflowKernel,
    canonical_payload_hash,
)
from .models import (
    CapabilityDescriptor,
    CapabilityInvocationContext,
    CapabilityResult,
    ExecutionTelemetry,
    IdempotencyClass,
    SideEffectClass,
)
from .registry import CapabilityRegistration, CapabilityRegistry


class ApprovalEvidence(Protocol):
    id: str
    workflow_run_id: str
    workflow_step_id: str | None
    task_attempt_id: str | None


TelemetrySink = Callable[[ExecutionTelemetry], Any]


class ExecutionGateway:
    """Executes registered capabilities only after deterministic authorization."""

    def __init__(
        self,
        *,
        registry: CapabilityRegistry,
        kernel: WorkflowKernel,
        approvals: ApprovalManager | None = None,
        telemetry: TelemetrySink | None = None,
    ) -> None:
        self._registry = registry
        self._kernel = kernel
        self._approvals = approvals
        self._telemetry = telemetry

    @property
    def approvals(self) -> ApprovalManager | None:
        return self._approvals

    async def invoke(
        self,
        claim: ExecutionClaimRecord,
        descriptor: CapabilityDescriptor | str | None = None,
        payload: Mapping[str, Any] | None = None,
        policy: PolicyDecision | None = None,
        approval: ApprovalEvidence | None = None,
        *,
        capability_id: str | None = None,
    ) -> CapabilityResult:
        """Resolve, authorize, invoke, classify, fence-persist, then emit telemetry."""
        registration = self._resolve(descriptor, capability_id)
        if registration is None:
            return CapabilityResult(
                code=ExecutionResultCode.PERMANENT_FAILURE,
                reason_code="capability_not_found",
            )
        capability = registration.descriptor
        denied = self._authorize(capability, policy)
        if denied is not None:
            return denied
        if payload is None or not isinstance(payload, Mapping):
            return CapabilityResult(
                code=ExecutionResultCode.VALIDATION_FAILURE,
                reason_code="invalid_capability_payload",
            )
        raw_payload = dict(payload)
        try:
            typed_payload = capability.input_model.model_validate(
                raw_payload,
                strict=True,
            )
        except (ValidationError, TypeError, ValueError):
            return CapabilityResult(
                code=ExecutionResultCode.VALIDATION_FAILURE,
                reason_code="invalid_capability_payload",
            )
        idempotency_key = self._idempotency_key(capability, raw_payload)
        if idempotency_key is False:
            return CapabilityResult(
                code=ExecutionResultCode.VALIDATION_FAILURE,
                reason_code="idempotency_key_required",
            )
        typed_payload, model_id, provider, routing_denied = self._authorized_routing(
            capability,
            typed_payload,
            policy,
        )
        if routing_denied is not None:
            return routing_denied
        if policy is not None and (
            policy.decision == "REQUIRE_APPROVAL"
            or policy.effective_constraints.approval_required
        ):
            try:
                effective_payload = typed_payload.model_dump(
                    mode="json",
                    exclude_unset=True,
                )
                canonical_payload_hash(effective_payload)
            except Exception:
                return CapabilityResult(
                    code=ExecutionResultCode.VALIDATION_FAILURE,
                    reason_code="invalid_approval_payload",
                )
            approved = await self._verify_approval(
                claim,
                capability.capability_id,
                effective_payload,
                approval,
            )
            if approved is not True:
                return CapabilityResult(
                    code=ExecutionResultCode.POLICY_DENIED,
                    reason_code=(
                        "approval_required" if approval is None else "approval_invalid"
                    ),
                )

        started_at = self._kernel.clock.now()
        deadline, timeout_seconds = self._deadline(capability, policy, started_at)
        context = CapabilityInvocationContext(
            deadline=deadline,
            budgets=policy.effective_constraints.budgets,
            idempotency_key=(
                idempotency_key if isinstance(idempotency_key, str) else None
            ),
            data_egress=policy.effective_constraints.data_egress,
            allowed_models=policy.effective_constraints.allowed_models,
            allowed_providers=policy.effective_constraints.allowed_providers,
            model_id=model_id,
            provider=provider,
        )
        result = await self._invoke_adapter(
            registration,
            typed_payload,
            context,
            timeout_seconds,
        )
        result = self._classify(
            result,
            capability,
            claim,
            idempotency_key=(
                idempotency_key if isinstance(idempotency_key, str) else None
            ),
        )
        finished_at = self._kernel.clock.now()
        latency_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
        metadata: dict[str, object] = {
            "reason_code": result.reason_code,
            "retry_allowed": result.retry_allowed,
            "side_effect_class": capability.side_effect_class.value,
            "idempotency_class": capability.idempotency_class.value,
        }
        if isinstance(idempotency_key, str):
            metadata["idempotency_key_hash"] = _hash_reference(idempotency_key)
        persisted = await self._kernel.persist_execution_result(
            claim,
            execution_role=(
                "artifact"
                if capability.side_effect_class is SideEffectClass.ARTIFACT_GENERATION
                else "tool"
            ),
            capability_id=capability.capability_id,
            capability_version=capability.version,
            result_class=result.code.value,
            started_at=started_at,
            finished_at=finished_at,
            latency_ms=latency_ms,
            metadata=metadata,
            outcome_unknown=(
                {
                    "idempotency_class": capability.idempotency_class.value,
                    "reconciliation_reference": result.reconciliation_reference,
                }
                if result.code is ExecutionResultCode.OUTCOME_UNKNOWN
                else None
            ),
        )
        if not persisted:
            result = CapabilityResult(
                code=ExecutionResultCode.PERMANENT_FAILURE,
                reason_code="claim_lost",
            )
        await self._emit_telemetry(
            ExecutionTelemetry(
                capability_id=capability.capability_id,
                capability_version=capability.version,
                result_code=result.code,
                reason_code=result.reason_code,
                retry_allowed=result.retry_allowed,
                latency_ms=latency_ms,
                persisted=persisted,
            )
        )
        return result

    def _resolve(
        self,
        descriptor: CapabilityDescriptor | str | None,
        capability_id: str | None,
    ) -> CapabilityRegistration | None:
        requested = capability_id
        if requested is None and isinstance(descriptor, CapabilityDescriptor):
            requested = descriptor.capability_id
        elif requested is None and isinstance(descriptor, str):
            requested = descriptor
        if not isinstance(requested, str):
            return None
        try:
            registration = self._registry.resolve(requested)
        except LookupError:
            return None
        if (
            isinstance(descriptor, CapabilityDescriptor)
            and descriptor != registration.descriptor
        ):
            return None
        return registration

    @staticmethod
    def _authorize(
        capability: CapabilityDescriptor,
        policy: PolicyDecision | None,
    ) -> CapabilityResult | None:
        if not isinstance(policy, PolicyDecision) or policy.decision == "DENY":
            return CapabilityResult(
                code=ExecutionResultCode.POLICY_DENIED,
                reason_code="policy_denied",
            )
        allowed = policy.effective_constraints.allowed_capabilities
        if allowed is None or capability.capability_id not in allowed:
            return CapabilityResult(
                code=ExecutionResultCode.POLICY_DENIED,
                reason_code="capability_not_authorized",
            )
        if capability.required_permissions:
            return CapabilityResult(
                code=ExecutionResultCode.POLICY_DENIED,
                reason_code="permission_not_authorized",
            )
        if (
            capability.requires_data_egress
            or capability.side_effect_class is SideEffectClass.READ_ONLY_EXTERNAL
        ) and not policy.effective_constraints.data_egress:
            return CapabilityResult(
                code=ExecutionResultCode.POLICY_DENIED,
                reason_code="data_egress_denied",
            )
        return None

    @staticmethod
    def _authorized_routing(
        capability: CapabilityDescriptor,
        payload: BaseModel,
        policy: PolicyDecision,
    ) -> tuple[BaseModel, str | None, str | None, CapabilityResult | None]:
        constraints = policy.effective_constraints
        model_id: str | None = None
        provider: str | None = None
        if capability.uses_model_routing:
            requested_model = getattr(payload, "model_id", None)
            forced_model = constraints.forced_model
            if (
                forced_model is not None
                and requested_model is not None
                and requested_model != forced_model
            ):
                return (
                    payload,
                    None,
                    None,
                    CapabilityResult(
                        code=ExecutionResultCode.POLICY_DENIED,
                        reason_code="forced_model_mismatch",
                    ),
                )
            model_id = forced_model or requested_model
            if model_id is None and constraints.allowed_models is not None:
                return (
                    payload,
                    None,
                    None,
                    CapabilityResult(
                        code=ExecutionResultCode.POLICY_DENIED,
                        reason_code="model_selection_required",
                    ),
                )
            if (
                model_id is not None
                and constraints.allowed_models is not None
                and model_id not in constraints.allowed_models
            ):
                return (
                    payload,
                    None,
                    None,
                    CapabilityResult(
                        code=ExecutionResultCode.POLICY_DENIED,
                        reason_code="model_not_authorized",
                    ),
                )
            if forced_model is not None:
                payload = payload.model_copy(update={"model_id": forced_model})
        if capability.uses_provider_routing:
            provider = getattr(payload, "provider", None)
            if provider is None and constraints.allowed_providers is not None:
                return (
                    payload,
                    model_id,
                    None,
                    CapabilityResult(
                        code=ExecutionResultCode.POLICY_DENIED,
                        reason_code="provider_selection_required",
                    ),
                )
            if (
                provider is not None
                and constraints.allowed_providers is not None
                and provider not in constraints.allowed_providers
            ):
                return (
                    payload,
                    model_id,
                    None,
                    CapabilityResult(
                        code=ExecutionResultCode.POLICY_DENIED,
                        reason_code="provider_not_authorized",
                    ),
                )
        return payload, model_id, provider, None

    @staticmethod
    def _idempotency_key(
        capability: CapabilityDescriptor,
        payload: Mapping[str, Any],
    ) -> str | bool | None:
        required = capability.idempotency_class in {
            IdempotencyClass.IDEMPOTENT_WITH_KEY,
            IdempotencyClass.CHECK_BEFORE_RETRY,
        }
        value = payload.get("idempotency_key")
        if value is None:
            return False if required else None
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            return False
        return value

    async def _verify_approval(
        self,
        claim: ExecutionClaimRecord,
        capability_id: str,
        payload: Mapping[str, Any],
        approval: ApprovalEvidence | None,
    ) -> bool:
        if (
            self._approvals is None
            or approval is None
            or approval.workflow_step_id is None
            or approval.task_attempt_id != claim.task_attempt_id
        ):
            return False
        try:
            return await self._approvals.is_valid(
                approval.id,
                workflow_run_id=approval.workflow_run_id,
                workflow_step_id=approval.workflow_step_id,
                task_attempt_id=claim.task_attempt_id,
                capability_id=capability_id,
                payload=payload,
                now=self._kernel.clock.now(),
            )
        except Exception:
            return False

    @staticmethod
    def _deadline(
        capability: CapabilityDescriptor,
        policy: PolicyDecision,
        now: datetime,
    ) -> tuple[datetime | None, float | None]:
        normalized_now = _aware_utc(now)
        candidates: list[datetime] = []
        policy_deadline = policy.effective_constraints.deadline
        if policy_deadline is not None:
            candidates.append(policy_deadline.astimezone(timezone.utc))
        if capability.default_timeout_seconds is not None:
            candidates.append(
                normalized_now + timedelta(seconds=capability.default_timeout_seconds)
            )
        if not candidates:
            return None, None
        deadline = min(candidates)
        return deadline, max(0.0, (deadline - normalized_now).total_seconds())

    async def _invoke_adapter(
        self,
        registration: CapabilityRegistration,
        payload: BaseModel,
        context: CapabilityInvocationContext,
        timeout_seconds: float | None,
    ) -> CapabilityResult:
        try:
            if timeout_seconds is None:
                raw_result = await registration.adapter.invoke(payload, context)
            else:
                async with asyncio.timeout(timeout_seconds):
                    raw_result = await registration.adapter.invoke(payload, context)
        except TimeoutError:
            return self._timeout_result(registration.descriptor)
        except Exception:
            if self._outcome_is_ambiguous(registration.descriptor):
                return CapabilityResult(
                    code=ExecutionResultCode.OUTCOME_UNKNOWN,
                    reason_code="capability_exception_ambiguous",
                )
            return CapabilityResult(
                code=ExecutionResultCode.PERMANENT_FAILURE,
                reason_code="capability_failed",
            )
        if not isinstance(raw_result, CapabilityResult):
            if self._outcome_is_ambiguous(registration.descriptor):
                return CapabilityResult(
                    code=ExecutionResultCode.OUTCOME_UNKNOWN,
                    reason_code="capability_result_ambiguous",
                )
            return CapabilityResult(
                code=ExecutionResultCode.VALIDATION_FAILURE,
                reason_code="invalid_capability_result",
            )
        if raw_result.code is not ExecutionResultCode.SUCCESS:
            return raw_result.model_copy(update={"output": None})
        try:
            serialized = (
                raw_result.output.model_dump(mode="json")
                if isinstance(raw_result.output, BaseModel)
                else raw_result.output
            )
            output = registration.descriptor.output_model.model_validate(
                serialized,
                strict=True,
            )
        except Exception:
            if self._outcome_is_ambiguous(registration.descriptor):
                return CapabilityResult(
                    code=ExecutionResultCode.OUTCOME_UNKNOWN,
                    reason_code="capability_result_ambiguous",
                )
            return CapabilityResult(
                code=ExecutionResultCode.VALIDATION_FAILURE,
                reason_code="invalid_capability_result",
            )
        return raw_result.model_copy(update={"output": output})

    @staticmethod
    def _timeout_result(capability: CapabilityDescriptor) -> CapabilityResult:
        ambiguous = ExecutionGateway._outcome_is_ambiguous(capability)
        return CapabilityResult(
            code=(
                ExecutionResultCode.OUTCOME_UNKNOWN
                if ambiguous
                else ExecutionResultCode.TIMEOUT
            ),
            reason_code=(
                "capability_timeout_ambiguous" if ambiguous else "capability_timeout"
            ),
            retry_allowed=not ambiguous,
        )

    @staticmethod
    def _outcome_is_ambiguous(capability: CapabilityDescriptor) -> bool:
        return (
            capability.side_effect_class is SideEffectClass.COMMIT_SIDE_EFFECT
            or capability.idempotency_class
            in {
                IdempotencyClass.CHECK_BEFORE_RETRY,
                IdempotencyClass.NON_RETRYABLE_SIDE_EFFECT,
            }
        )

    @staticmethod
    def _classify(
        result: CapabilityResult,
        capability: CapabilityDescriptor,
        claim: ExecutionClaimRecord,
        *,
        idempotency_key: str | None,
    ) -> CapabilityResult:
        retry_allowed = bool(
            result.retry_allowed
            and capability.idempotency_class
            in {
                IdempotencyClass.IDEMPOTENT,
                IdempotencyClass.IDEMPOTENT_WITH_KEY,
            }
            and result.code
            in {ExecutionResultCode.TIMEOUT, ExecutionResultCode.TRANSIENT_FAILURE}
        )
        if result.code is ExecutionResultCode.OUTCOME_UNKNOWN:
            reference_material = "|".join(
                (
                    capability.capability_id,
                    str(capability.version),
                    claim.id,
                    str(claim.fencing_token),
                    idempotency_key or "no-key",
                )
            )
            return result.model_copy(
                update={
                    "output": None,
                    "retry_allowed": False,
                    "reconciliation_reference": _hash_reference(reference_material),
                }
            )
        return result.model_copy(
            update={
                "retry_allowed": retry_allowed,
                "reconciliation_reference": None,
            }
        )

    async def _emit_telemetry(self, event: ExecutionTelemetry) -> None:
        if self._telemetry is None:
            return
        try:
            outcome = self._telemetry(event)
            if inspect.isawaitable(outcome):
                await outcome
        except Exception:
            return


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _hash_reference(value: str) -> str:
    return "sha256." + hashlib.sha256(value.encode("utf-8")).hexdigest()
