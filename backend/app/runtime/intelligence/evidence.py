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
    async def from_evaluation_store(cls, evaluation_store: object) -> "EvidenceStore":
        """Rebuild only evidence whose immutable observation lineage verifies.

        The durable row is deliberately insufficient authority on its own.  This
        makes old/incomplete rows inert rather than allowing a restart to turn a
        caller-constructed aggregate into routing evidence.
        """
        load_evidence = getattr(evaluation_store, "load_promoted_model_evidence", None)
        load_observations = getattr(evaluation_store, "load_routing_observations", None)
        if not callable(load_evidence) or not callable(load_observations):
            raise TypeError("evaluation store lacks typed routing evidence loaders")
        store = cls()
        records = await load_evidence()
        for record in records:
            ids = getattr(record, "observation_ids_json", None)
            if (
                getattr(record, "evidence_type", None) != "promoted"
                or not isinstance(ids, list)
                or not ids
            ):
                continue
            try:
                durable = await load_observations(tuple(ids))
                if len(durable) != len(ids):
                    continue
                durable_ids = tuple(item.id for item in durable)
                if len(set(durable_ids)) != len(durable_ids) or set(durable_ids) != set(
                    ids
                ):
                    continue
                by_id = {
                    item.observation_id: item
                    for item in (_observation_from_record(value) for value in durable)
                }
                candidate = _qualified_evidence(
                    tuple(by_id[item] for item in ids),
                    {
                        "qualification_id": record.qualification_id,
                        "qualification_version": record.qualification_version,
                        "minimum_sample_size": getattr(
                            record, "minimum_sample_size", None
                        ),
                    },
                )
            except (KeyError, TypeError, ValueError):
                continue
            if not _matches_record(candidate, record):
                continue
            store._activate(candidate)
        return store


async def promote_model_evidence(
    store: EvidenceStore,
    evaluation_store: object,
    observation_ids: tuple[str, ...],
    qualification: Mapping[str, object],
) -> ModelEvidence:
    """Persist qualified evidence, then and only then make it routing-active."""
    observations = store.observations(observation_ids)
    candidate = _qualified_evidence(observations, qualification)
    persist = getattr(evaluation_store, "record_promoted_model_evidence", None)
    if not callable(persist):
        raise TypeError("evaluation store cannot persist promoted model evidence")
    await persist(candidate, observations)
    return store._activate(candidate)


def _qualified_evidence(
    observations: tuple[EvidenceObservation, ...],
    qualification: Mapping[str, object],
) -> ModelEvidence:
    observation_ids = tuple(item.observation_id for item in observations)
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
    return ModelEvidence(
        evidence_id=_evidence_id(
            qualification_id,
            qualification_version,
            minimum_sample_size,
            observation_ids,
        ),
        task_id=first.task_id,
        task_version=first.task_version,
        model_id=first.model_id,
        model_version=first.model_version,
        provider=first.provider,
        quality_score=weighted_quality,
        sample_size=total_sample_size,
        qualification_id=qualification_id,
        qualification_version=qualification_version,
        minimum_sample_size=minimum_sample_size,
        observation_ids=tuple(sorted(observation_ids)),
    )


def _evidence_id(
    qualification_id: str,
    qualification_version: int,
    minimum_sample_size: int,
    observation_ids: tuple[str, ...],
) -> str:
    material = "|".join(
        (
            qualification_id,
            str(qualification_version),
            str(minimum_sample_size),
            *sorted(observation_ids),
        )
    )
    return "evidence." + hashlib.sha256(material.encode()).hexdigest()[:24]


def _matches_record(candidate: ModelEvidence, record: object) -> bool:
    return (
        all(
            getattr(record, name, None) == expected
            for name, expected in (
                ("id", candidate.evidence_id),
                ("task_id", candidate.task_id),
                ("task_version", candidate.task_version),
                ("model_id", candidate.model_id),
                ("model_version", candidate.model_version),
                ("provider", candidate.provider),
                ("qualification_id", candidate.qualification_id),
                ("qualification_version", candidate.qualification_version),
                ("minimum_sample_size", candidate.minimum_sample_size),
                ("sample_size", candidate.sample_size),
            )
        )
        and getattr(record, "quality_score", None) == candidate.quality_score
    )


def _observation_from_record(record: object) -> EvidenceObservation:
    if getattr(record, "routing_observation_type", None) != "routing_observation":
        raise ValueError("invalid routing observation type")
    return EvidenceObservation(
        observation_id=record.id,
        task_id=record.task_id,
        task_version=record.task_version,
        model_id=record.model_id,
        model_version=record.model_version,
        provider=record.provider,
        quality_score=float(record.quality_score),
        sample_size=record.sample_size,
    )
