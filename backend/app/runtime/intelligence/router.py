"""Explainable deterministic router with fixed gate ordering."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..control import EffectiveConstraints, PolicyDecision
from ..contracts import ModelCapabilityRequirements, TaskSpec
from .evidence import EvidenceStore
from .models import (
    ModelDescriptor,
    RoutingCandidate,
    RoutingDecision,
    RoutingMode,
    RoutingPreference,
    RoutingRequirements,
    RoutingStage,
)
from .registry import ModelRegistry

if TYPE_CHECKING:
    from ..storage import EvaluationStore

_STAGES = tuple(
    RoutingStage(name)
    for name in ("capability", "quality", "policy", "evidence", "fallback")
)


class ModelRouter:
    def __init__(
        self, registry: ModelRegistry, *, evidence_store: EvidenceStore | None = None
    ) -> None:
        self._registry = registry
        self._evidence_store = evidence_store or EvidenceStore()

    def route(
        self,
        requirements: RoutingRequirements | ModelCapabilityRequirements | TaskSpec,
        policy: PolicyDecision | EffectiveConstraints | None,
        preference: RoutingPreference,
    ) -> RoutingDecision:
        resolved_requirements = RoutingRequirements.from_value(requirements)
        constraints, policy_denied = _policy_constraints(policy)
        candidates: list[RoutingCandidate] = []
        eligible: list[tuple[ModelDescriptor, float, dict[str, float]]] = []
        for descriptor in self._registry.descriptors():
            exclusions: list[str] = []
            missing = sorted(
                resolved_requirements.required_capabilities - descriptor.capabilities
            )
            exclusions.extend(
                f"capability.{capability}_missing" for capability in missing
            )
            if resolved_requirements.minimum_context_window and (
                descriptor.context_window is None
                or descriptor.context_window
                < resolved_requirements.minimum_context_window
            ):
                exclusions.append("capability.context_window_too_small")
            if _privacy_level(descriptor.privacy_characteristics) < _privacy_level(
                resolved_requirements.privacy_requirement
            ):
                exclusions.append("privacy.requirement_not_met")
            if descriptor.quality_score < resolved_requirements.quality_floor:
                exclusions.append("quality.floor_not_met")
            exclusions.extend(
                _policy_exclusions(descriptor, constraints, policy_denied)
            )
            components = {
                "base": float(descriptor.base_rank),
                "evidence": 0.0,
                "preference": 0.0,
            }
            if not exclusions:
                evidence = self._evidence_store.active_for(
                    task_id=resolved_requirements.task_id,
                    task_version=resolved_requirements.task_version,
                    model_id=descriptor.model_id,
                    model_version=descriptor.version,
                    provider=descriptor.provider,
                )
                if evidence:
                    components["evidence"] = (
                        max(item.quality_score for item in evidence) * 100.0
                    )
                if (
                    preference.mode is RoutingMode.PREFER
                    and preference.model_id == descriptor.model_id
                ):
                    components["preference"] = 1_000.0
                eligible.append((descriptor, sum(components.values()), components))
            candidates.append(
                RoutingCandidate(
                    model_id=descriptor.model_id,
                    model_version=descriptor.version,
                    provider=descriptor.provider,
                    model_name=descriptor.model_name,
                    eligible=not exclusions,
                    excluded_reason_codes=tuple(exclusions),
                    rank_components=components,
                    final_rank=sum(components.values()) if not exclusions else None,
                )
            )
        selected: ModelDescriptor | None = None
        if preference.mode is RoutingMode.FORCE:
            selected = next(
                (
                    item[0]
                    for item in eligible
                    if item[0].model_id == preference.model_id
                ),
                None,
            )
            candidates = [
                candidate
                if not candidate.eligible or candidate.model_id == preference.model_id
                else RoutingCandidate(
                    model_id=candidate.model_id,
                    model_version=candidate.model_version,
                    provider=candidate.provider,
                    model_name=candidate.model_name,
                    eligible=False,
                    excluded_reason_codes=candidate.excluded_reason_codes
                    + ("fallback.force_other_model",),
                    rank_components=candidate.rank_components,
                    final_rank=None,
                )
                for candidate in candidates
            ]
        elif eligible:
            selected = max(eligible, key=lambda item: (item[1], item[0].model_id))[0]
        fallback_model_ids = (
            ()
            if preference.mode is RoutingMode.FORCE
            else tuple(
                model_id
                for model_id in preference.fallback_model_ids
                if any(item[0].model_id == model_id for item in eligible)
                and model_id != (None if selected is None else selected.model_id)
            )
        )
        return RoutingDecision(
            requirements=resolved_requirements,
            candidates=tuple(candidates),
            selected_descriptor=selected,
            stages=_STAGES,
            evidence_snapshot_id=self._evidence_store.snapshot_id(),
            fallback_model_ids=fallback_model_ids,
            selection_proof=None
            if selected is None
            else self._registry.issue_selection(selected),
        )

    async def persist_decision(
        self,
        store: "EvaluationStore",
        *,
        task_attempt_id: str,
        capability_id: str,
        decision: RoutingDecision,
    ) -> object:
        selected = decision.selected_descriptor
        return await store.record_routing_decision(
            task_attempt_id=task_attempt_id,
            router_id="model.router",
            router_version=1,
            capability_id=capability_id,
            task_id=decision.requirements.task_id,
            task_version=decision.requirements.task_version,
            model_id=None if selected is None else selected.model_id,
            model_version=None if selected is None else selected.version,
            provider=None if selected is None else selected.provider,
            candidate_snapshot_json=[
                candidate.as_snapshot() for candidate in decision.candidates
            ],
            routing_policy_version=decision.routing_policy_version,
            evidence_snapshot_id=decision.evidence_snapshot_id,
            reason_codes_json=[]
            if selected is not None
            else ["fallback.no_eligible_model"],
        )


def _policy_constraints(
    policy: PolicyDecision | EffectiveConstraints | None,
) -> tuple[EffectiveConstraints | None, bool]:
    if policy is None:
        return None, False
    if isinstance(policy, PolicyDecision):
        return policy.effective_constraints, policy.decision == "DENY"
    return policy, False


def _policy_exclusions(
    descriptor: ModelDescriptor,
    constraints: EffectiveConstraints | None,
    policy_denied: bool,
) -> list[str]:
    if constraints is None:
        return []
    exclusions: list[str] = []
    if policy_denied:
        exclusions.append("policy.denied")
    if not descriptor.enabled:
        exclusions.append("policy.model_disabled")
    if (
        constraints.allowed_models is not None
        and descriptor.model_id not in constraints.allowed_models
    ):
        exclusions.append("policy.model_not_allowed")
    if (
        constraints.allowed_providers is not None
        and descriptor.provider not in constraints.allowed_providers
    ):
        exclusions.append("policy.provider_not_allowed")
    if not constraints.data_egress and descriptor.local_or_cloud != "local":
        exclusions.append("privacy.data_egress_denied")
    return exclusions


def _privacy_level(value: str) -> int:
    return {"public": 0, "provider_configured": 1, "confidential": 2, "local": 3}.get(
        value, 0
    )
