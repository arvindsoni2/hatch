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

    def _activate(self, evidence: ModelEvidence) -> ModelEvidence:
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

    @classmethod
    def from_promoted_records(cls, records: object) -> "EvidenceStore":
        store = cls()
        for record in records:
            if not all(
                (
                    record.model_version,
                    record.qualification_id,
                    record.qualification_version,
                    record.observation_ids_json,
                    record.quality_score is not None,
                )
            ):
                continue
            store._activate(
                ModelEvidence(
                    evidence_id=record.id,
                    task_id=record.task_id,
                    task_version=record.task_version,
                    model_id=record.model_id,
                    model_version=record.model_version,
                    provider=record.provider,
                    quality_score=float(record.quality_score),
                    sample_size=record.sample_size,
                    qualification_id=record.qualification_id,
                    qualification_version=record.qualification_version,
                    observation_ids=tuple(record.observation_ids_json),
                )
            )
        return store


def promote_model_evidence(
    store: EvidenceStore,
    observation_ids: tuple[str, ...],
    qualification: Mapping[str, object],
) -> ModelEvidence:
    """Create routing-active aggregate evidence only after bounded qualification."""
    if not observation_ids or len(observation_ids) > 100:
        raise ValueError("promotion requires between one and 100 observations")
    if len(set(observation_ids)) != len(observation_ids):
        raise ValueError("duplicate observation IDs are not allowed")
    qualification_id = qualification.get("qualification_id")
    minimum_sample_size = qualification.get("minimum_sample_size")
    qualification_version = qualification.get("qualification_version")
    if not isinstance(qualification_id, str) or not qualification_id:
        raise ValueError("qualification_id is required")
    if (
        isinstance(minimum_sample_size, bool)
        or not isinstance(minimum_sample_size, int)
        or not 1 <= minimum_sample_size <= 1_000_000
    ):
        raise ValueError("minimum_sample_size must be bounded positive integer")
    if (
        isinstance(qualification_version, bool)
        or not isinstance(qualification_version, int)
        or not 1 <= qualification_version <= 10_000
    ):
        raise ValueError("qualification_version must be bounded positive integer")
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
            (
                qualification_id
                + "|"
                + str(qualification_version)
                + "|"
                + "|".join(sorted(observation_ids))
            ).encode()
        ).hexdigest()[:24]
    )
    return store._activate(
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
            qualification_version=qualification_version,
            observation_ids=tuple(sorted(observation_ids)),
        )
    )


async def persist_promoted_model_evidence(
    evaluation_store: object, evidence: ModelEvidence
) -> ModelEvidence:
    """Persist one already-qualified aggregate through the runtime UoW seam."""
    record = getattr(evaluation_store, "record_model_evidence", None)
    if not callable(record):
        raise TypeError("evaluation store cannot persist model evidence")
    await record(
        id=evidence.evidence_id,
        task_id=evidence.task_id,
        task_version=evidence.task_version,
        model_id=evidence.model_id,
        model_version=evidence.model_version,
        provider=evidence.provider,
        evidence_type="promoted",
        qualification_id=evidence.qualification_id,
        qualification_version=evidence.qualification_version,
        observation_ids_json=list(evidence.observation_ids),
        quality_score=evidence.quality_score,
        metrics_json={},
        sample_size=evidence.sample_size,
    )
    return evidence
