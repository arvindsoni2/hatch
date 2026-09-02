"""Typed, metadata-only contracts for deterministic model selection."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

from ..contracts import ModelCapabilityRequirements, TaskSpec

_STABLE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")


def _stable(value: str, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 128
        or not _STABLE_IDENTIFIER.fullmatch(value)
    ):
        raise ValueError(f"{field_name} must be a bounded stable identifier")
    return value


@dataclass(frozen=True)
class ModelDescriptor:
    """Trusted static capabilities for one configured provider/model pairing."""

    model_id: str
    version: str
    provider: str
    model_name: str
    capabilities: frozenset[str] = frozenset()
    structured_output: bool = True
    tool_calling: bool = False
    context_window: int | None = None
    reasoning_class: str = "standard"
    local_or_cloud: str = "cloud"
    estimated_latency_class: str = "standard"
    estimated_cost_class: str = "standard"
    hardware_requirements: str | None = None
    privacy_characteristics: str = "provider_configured"
    enabled: bool = True
    quality_score: float = 0.0
    base_rank: float = 0.0

    def __post_init__(self) -> None:
        _stable(self.model_id, "model_id")
        _stable(self.provider, "provider")
        if (
            not isinstance(self.version, str)
            or not self.version
            or len(self.version) > 128
        ):
            raise ValueError("version must be a bounded non-empty string")
        if (
            not isinstance(self.model_name, str)
            or not self.model_name
            or len(self.model_name) > 512
        ):
            raise ValueError(
                "model_name must be a bounded non-empty provider-native name"
            )
        capabilities = frozenset(self.capabilities)
        for capability in capabilities:
            _stable(capability, "capabilities")
        object.__setattr__(self, "capabilities", capabilities)
        if self.structured_output:
            object.__setattr__(
                self, "capabilities", capabilities | {"structured_output"}
            )
        if self.tool_calling:
            object.__setattr__(
                self, "capabilities", self.capabilities | {"tool_calling"}
            )
        if self.local_or_cloud not in {"local", "cloud"}:
            raise ValueError("local_or_cloud must be local or cloud")
        if not 0.0 <= self.quality_score <= 1.0:
            raise ValueError("quality_score must be between zero and one")


@dataclass(frozen=True)
class RoutingRequirements:
    """Task-scoped requirements used by the router, never user preferences."""

    task_id: str
    task_version: int
    required_capabilities: frozenset[str] = frozenset()
    quality_floor: float = 0.0
    minimum_context_window: int = 0
    privacy_requirement: str = "provider_configured"

    def __post_init__(self) -> None:
        _stable(self.task_id, "task_id")
        if isinstance(self.task_version, bool) or self.task_version < 1:
            raise ValueError("task_version must be positive")
        capabilities = frozenset(self.required_capabilities)
        for capability in capabilities:
            _stable(capability, "required_capabilities")
        object.__setattr__(self, "required_capabilities", capabilities)
        if not 0.0 <= self.quality_floor <= 1.0:
            raise ValueError("quality_floor must be between zero and one")
        if (
            isinstance(self.minimum_context_window, bool)
            or not 0 <= self.minimum_context_window <= 2_000_000
        ):
            raise ValueError("minimum_context_window must be bounded")
        if self.privacy_requirement not in {
            "public",
            "provider_configured",
            "confidential",
            "local",
        }:
            raise ValueError("privacy_requirement is not supported")

    @classmethod
    def from_value(
        cls, value: "RoutingRequirements | ModelCapabilityRequirements | TaskSpec"
    ) -> "RoutingRequirements":
        if isinstance(value, cls):
            return value
        if isinstance(value, ModelCapabilityRequirements):
            return cls(
                task_id="model.requirements",
                task_version=1,
                required_capabilities=frozenset(value.required_capabilities),
            )
        if isinstance(value, TaskSpec):
            return cls(
                task_id=value.task_id,
                task_version=value.version,
                required_capabilities=frozenset(
                    value.model_requirements.required_capabilities
                ),
            )
        raise TypeError("routing requirements must be a TaskSpec or model requirements")


class RoutingMode(str, Enum):
    AUTO = "auto"
    PREFER = "prefer"
    FORCE = "force"


@dataclass(frozen=True)
class RoutingPreference:
    """Selection intent applied only after every mandatory eligibility gate."""

    mode: RoutingMode = RoutingMode.AUTO
    model_id: str | None = None
    fallback_model_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", RoutingMode(self.mode))
        fallbacks = tuple(self.fallback_model_ids)
        if len(fallbacks) > 8 or len(set(fallbacks)) != len(fallbacks):
            raise ValueError("fallback model IDs must be unique and bounded")
        for fallback in fallbacks:
            _stable(fallback, "fallback_model_ids")
        object.__setattr__(self, "fallback_model_ids", fallbacks)
        if self.mode is RoutingMode.AUTO and self.model_id is not None:
            raise ValueError("AUTO routing does not name a model")
        if self.mode is not RoutingMode.AUTO:
            if self.model_id is None:
                raise ValueError("PREFER and FORCE routing require a model_id")
            _stable(self.model_id, "model_id")

    @classmethod
    def auto(cls, *, fallback_model_ids: tuple[str, ...] = ()) -> "RoutingPreference":
        return cls(fallback_model_ids=fallback_model_ids)

    @classmethod
    def prefer(
        cls, model_id: str, *, fallback_model_ids: tuple[str, ...] = ()
    ) -> "RoutingPreference":
        return cls(RoutingMode.PREFER, model_id, fallback_model_ids)

    @classmethod
    def force(
        cls, model_id: str, *, fallback_model_ids: tuple[str, ...] = ()
    ) -> "RoutingPreference":
        return cls(RoutingMode.FORCE, model_id, fallback_model_ids)


@dataclass(frozen=True)
class RoutingCandidate:
    model_id: str
    model_version: str
    provider: str
    model_name: str
    eligible: bool
    excluded_reason_codes: tuple[str, ...]
    rank_components: Mapping[str, float]
    final_rank: float | None

    def as_snapshot(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "provider": self.provider,
            "model_name": self.model_name,
            "eligible": self.eligible,
            "excluded_reason_codes": list(self.excluded_reason_codes),
            "rank_components": dict(self.rank_components),
            "final_rank": self.final_rank,
        }


@dataclass(frozen=True)
class RoutingStage:
    name: str


@dataclass(frozen=True)
class RoutingDecision:
    requirements: RoutingRequirements
    candidates: tuple[RoutingCandidate, ...]
    selected_descriptor: ModelDescriptor | None
    stages: tuple[RoutingStage, ...]
    routing_policy_version: int = 1
    evidence_snapshot_id: str = "evidence.none"
    fallback_model_ids: tuple[str, ...] = ()
    selection_proof: object | None = None

    @property
    def selected_model_id(self) -> str | None:
        return (
            None
            if self.selected_descriptor is None
            else self.selected_descriptor.model_id
        )


@dataclass(frozen=True)
class EvidenceObservation:
    """Immutable metadata-only production observation, inactive until promotion."""

    observation_id: str
    task_id: str
    task_version: int
    model_id: str
    model_version: str
    provider: str
    quality_score: float
    sample_size: int

    def __post_init__(self) -> None:
        for name in ("observation_id", "task_id", "model_id", "provider"):
            _stable(getattr(self, name), name)
        if isinstance(self.task_version, bool) or self.task_version < 1:
            raise ValueError("task_version must be positive")
        if not self.model_version or len(self.model_version) > 128:
            raise ValueError("model_version must be bounded")
        if not 0.0 <= self.quality_score <= 1.0:
            raise ValueError("quality_score must be between zero and one")
        if isinstance(self.sample_size, bool) or not 1 <= self.sample_size <= 10_000:
            raise ValueError("sample_size must be between one and 10000")


@dataclass(frozen=True)
class ModelEvidence:
    evidence_id: str
    task_id: str
    task_version: int
    model_id: str
    model_version: str
    provider: str
    quality_score: float
    sample_size: int
    qualification_id: str
    qualification_version: int = 1
    observation_ids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for name in (
            "evidence_id",
            "task_id",
            "model_id",
            "provider",
            "qualification_id",
        ):
            _stable(getattr(self, name), name)
        if not self.model_version or len(self.model_version) > 128:
            raise ValueError("model_version must be bounded")
        if isinstance(self.task_version, bool) or self.task_version < 1:
            raise ValueError("task_version must be positive")
        if (
            isinstance(self.qualification_version, bool)
            or not 1 <= self.qualification_version <= 10_000
        ):
            raise ValueError("qualification_version must be bounded")
        if not 0.0 <= self.quality_score <= 1.0:
            raise ValueError("quality_score must be between zero and one")
        if isinstance(self.sample_size, bool) or not 1 <= self.sample_size <= 1_000_000:
            raise ValueError("sample_size must be bounded")
        ids = tuple(self.observation_ids)
        if not ids or len(ids) > 100 or len(set(ids)) != len(ids):
            raise ValueError("observation_ids must be unique and bounded")
        for observation_id in ids:
            _stable(observation_id, "observation_ids")
        object.__setattr__(self, "observation_ids", ids)
