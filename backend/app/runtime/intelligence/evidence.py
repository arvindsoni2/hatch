"""Explicit, deterministic promotion of immutable model observations."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from .models import EvidenceObservation, ModelEvidence


class EvidenceStore:
    """In-memory seam used by routing; recording never changes active evidence."""

    def __init__(self) -> None:
        self._observations: dict[str, EvidenceObservation] = {}
        self._promoted: dict[str, ModelEvidence] = {}

    def record(self, observation: EvidenceObservation) -> EvidenceObservation:
        if observation.observation_id in self._observations:
            raise ValueError("observation_id already recorded")
        self._observations[observation.observation_id] = observation
        return observation

    def observations(
        self, observation_ids: tuple[str, ...]
    ) -> tuple[EvidenceObservation, ...]:
        try:
            return tuple(
                self._observations[observation_id] for observation_id in observation_ids
            )
        except KeyError as error:
            raise LookupError("observation_not_found") from error

    def promote(self, evidence: ModelEvidence) -> ModelEvidence:
        self._promoted[evidence.evidence_id] = evidence
        return evidence

    def active_for(
        self,
        *,
        task_id: str,
        task_version: int,
        model_id: str,
        model_version: str,
        provider: str,
    ) -> tuple[ModelEvidence, ...]:
        return tuple(
            evidence
            for evidence in self._promoted.values()
            if (
                evidence.task_id,
                evidence.task_version,
                evidence.model_id,
                evidence.model_version,
                evidence.provider,
            )
            == (task_id, task_version, model_id, model_version, provider)
        )

    def snapshot_id(self) -> str:
        if not self._promoted:
            return "evidence.none"
        payload = "|".join(sorted(self._promoted))
        return "evidence." + hashlib.sha256(payload.encode()).hexdigest()[:24]


def promote_model_evidence(
    store: EvidenceStore,
    observation_ids: tuple[str, ...],
    qualification: Mapping[str, object],
) -> ModelEvidence:
    """Create routing-active aggregate evidence only after bounded qualification."""
    if not observation_ids or len(observation_ids) > 100:
        raise ValueError("promotion requires between one and 100 observations")
    qualification_id = qualification.get("qualification_id")
    minimum_sample_size = qualification.get("minimum_sample_size")
    if not isinstance(qualification_id, str) or not qualification_id:
        raise ValueError("qualification_id is required")
    if isinstance(minimum_sample_size, bool) or not isinstance(
        minimum_sample_size, int
    ):
        raise ValueError("minimum_sample_size must be an integer")
    observations = store.observations(observation_ids)
    first = observations[0]
    identity = (
        first.task_id,
        first.task_version,
        first.model_id,
        first.model_version,
        first.provider,
    )
    if any(
        (
            item.task_id,
            item.task_version,
            item.model_id,
            item.model_version,
            item.provider,
        )
        != identity
        for item in observations
    ):
        raise ValueError("observations must share task and model identity")
    total_sample_size = sum(item.sample_size for item in observations)
    if total_sample_size < minimum_sample_size:
        raise ValueError("qualification_sample_size_not_met")
    weighted_quality = (
        sum(item.quality_score * item.sample_size for item in observations)
        / total_sample_size
    )
    evidence_id = (
        "evidence."
        + hashlib.sha256(
            (qualification_id + "|" + "|".join(sorted(observation_ids))).encode()
        ).hexdigest()[:24]
    )
    return store.promote(
        ModelEvidence(
            evidence_id=evidence_id,
            task_id=first.task_id,
            task_version=first.task_version,
            model_id=first.model_id,
            model_version=first.model_version,
            provider=first.provider,
            quality_score=weighted_quality,
            sample_size=total_sample_size,
            qualification_id=qualification_id,
            observation_ids=tuple(sorted(observation_ids)),
        )
    )
