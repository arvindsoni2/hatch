"""Deterministic named-level report algorithms for conversational Coach sessions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, TypeAlias

from .coach_conversational_contracts import CONTENT_DIMENSIONS, REPORT_CONTRACT

Level: TypeAlias = Literal[
    "needs_work", "developing", "interview_ready", "strong", "not_assessed"
]

LEVEL_TO_ORDINAL: dict[Level, int] = {
    "needs_work": 1,
    "developing": 2,
    "interview_ready": 3,
    "strong": 4,
    "not_assessed": 0,
}
ORDINAL_TO_LEVEL: dict[int, Level] = {
    1: "needs_work",
    2: "developing",
    3: "interview_ready",
    4: "strong",
}
CRITICAL_DIMENSIONS = frozenset(
    {"relevance", "structure", "specificity", "role_depth"}
)


@dataclass(frozen=True)
class AcceptedAnswer:
    """The content-free evaluation projection needed by bundle aggregation."""

    attempt_id: str
    levels: Mapping[str, Level]
    target_dimension: str | None = None
    aggregation_role: Literal["root", "gap_repair", "primary_evidence"] = "root"


@dataclass(frozen=True)
class BundleDimension:
    level: Level
    contributor_attempt_ids: tuple[str, ...]
    adjustment_reason: str


@dataclass(frozen=True)
class ReportBuildClaim:
    session_id: str
    activity_version: int
    build_reason: Literal[
        "initial_completion",
        "transcript_deletion_rebuild",
        "reflection_update_rebuild",
        "manual_retry",
    ]
    job_id: str


class ReportRepository(Protocol):
    async def load_report_input_snapshot(
        self, session_id: str, activity_version: int
    ) -> ReportInputSnapshot | None: ...

    async def finalise_conversational_report(
        self,
        claim: ReportBuildClaim,
        report_json: dict[str, object],
        report_state: Literal["completed", "fallback"],
    ) -> bool: ...

    async def finalise_completed_session_report_rebuild(
        self,
        claim: ReportBuildClaim,
        report_json: dict[str, object],
        report_state: Literal["completed", "fallback"],
    ) -> bool: ...


@dataclass(frozen=True)
class ReportInputSnapshot:
    """Minimal immutable input boundary for deterministic report construction."""

    session_id: str
    activity_version: int
    retention_version: int
    accepted_root_bundles: tuple[tuple[AcceptedAnswer, tuple[AcceptedAnswer, ...]], ...]
    compatibility_key: str
    counts: Mapping[str, int] = field(default_factory=dict)
    candidate_reflection: Mapping[str, object] | None = None


@dataclass(frozen=True)
class ConversationalReportSnapshot:
    report_json: dict[str, object]
    report_state: Literal["completed", "fallback"]

    def persisted_json(self) -> dict[str, object]:
        """Return the analytical snapshot without the live retention overlay."""
        return dict(self.report_json)


def _level(value: object) -> Level:
    return value if value in LEVEL_TO_ORDINAL else "not_assessed"  # type: ignore[return-value]


def lower_median(levels: Sequence[Level | str]) -> Level:
    """Return the lower median of assessed named levels."""

    values = sorted(
        LEVEL_TO_ORDINAL[_level(level)]
        for level in levels
        if _level(level) != "not_assessed"
    )
    if len(values) < 2:
        return "not_assessed"
    return ORDINAL_TO_LEVEL[values[(len(values) - 1) // 2]]


def derive_session_level(levels: Mapping[str, Level | str]) -> Level:
    """Apply V6 §27.6's ordered readiness thresholds."""

    assessed = {
        dimension: _level(levels.get(dimension, "not_assessed"))
        for dimension in CONTENT_DIMENSIONS
    }
    assessed_levels = [
        level for level in assessed.values() if level != "not_assessed"
    ]
    assessed_count = len(assessed_levels)
    if assessed_count < 5:
        return "not_assessed"

    strong_count = sum(level == "strong" for level in assessed_levels)
    ready_or_strong_count = sum(
        level in {"interview_ready", "strong"} for level in assessed_levels
    )
    needs_work_count = sum(level == "needs_work" for level in assessed_levels)
    critical_assessed = all(assessed[name] != "not_assessed" for name in CRITICAL_DIMENSIONS)
    critical_needs_work = sum(assessed[name] == "needs_work" for name in CRITICAL_DIMENSIONS)
    non_critical_needs_work = sum(
        assessed[name] == "needs_work"
        for name in set(CONTENT_DIMENSIONS) - CRITICAL_DIMENSIONS
    )

    if (
        assessed_count == 7
        and strong_count >= 5
        and all(level in {"interview_ready", "strong"} for level in assessed.values())
        and critical_assessed
    ):
        return "strong"
    if (
        assessed_count >= 6
        and ready_or_strong_count >= 5
        and critical_assessed
        and critical_needs_work == 0
        and non_critical_needs_work <= 1
    ):
        return "interview_ready"
    if (
        assessed_count >= 5
        and ready_or_strong_count + sum(level == "developing" for level in assessed_levels) >= 5
        and critical_needs_work <= 1
        and needs_work_count <= 2
    ):
        return "developing"
    return "needs_work"


def aggregate_root_bundle(
    root: AcceptedAnswer,
    followups: Sequence[AcceptedAnswer],
    dimension: str,
) -> BundleDimension:
    """Aggregate one root answer and its accepted follow-ups for one dimension."""

    root_level = _level(root.levels.get(dimension, "not_assessed"))
    relevant = [
        followup
        for followup in followups
        if followup.target_dimension == dimension
        and _level(followup.levels.get(dimension, "not_assessed")) != "not_assessed"
    ]
    gap_repair = [
        item for item in relevant if item.aggregation_role == "gap_repair"
    ]
    primary = [
        item for item in relevant if item.aggregation_role == "primary_evidence"
    ]

    contributor_ids = (root.attempt_id,) + tuple(item.attempt_id for item in relevant)
    if root_level == "not_assessed":
        if not primary:
            return BundleDimension("not_assessed", contributor_ids, "root_unavailable")
        final = min(
            (_level(item.levels[dimension]) for item in primary),
            key=LEVEL_TO_ORDINAL.__getitem__,
        )
        return BundleDimension(final, contributor_ids, "root_unavailable_primary_evidence")

    upward = LEVEL_TO_ORDINAL[root_level]
    if any(LEVEL_TO_ORDINAL[_level(item.levels[dimension])] > upward for item in gap_repair):
        upward = min(upward + 1, LEVEL_TO_ORDINAL["strong"])

    if primary:
        downward = min(
            LEVEL_TO_ORDINAL[_level(item.levels[dimension])] for item in primary
        )
        final = ORDINAL_TO_LEVEL[min(upward, downward)]
        reason = "primary_evidence_floor" if downward < upward else "gap_repair"
    else:
        final = ORDINAL_TO_LEVEL[upward]
        reason = "gap_repair" if gap_repair else "root_only"
    return BundleDimension(final, contributor_ids, reason)


def build_conversational_report(
    snapshot: ReportInputSnapshot,
) -> ConversationalReportSnapshot:
    """Build deterministic report values from an immutable input snapshot."""

    dimensions: dict[str, Level] = {}
    for dimension in CONTENT_DIMENSIONS:
        bundle_levels = [
            aggregate_root_bundle(root, followups, dimension).level
            for root, followups in snapshot.accepted_root_bundles
        ]
        dimensions[dimension] = lower_median(bundle_levels)
    report: dict[str, object] = {
        "session_id": snapshot.session_id,
        "activity_version": snapshot.activity_version,
        "session_level": derive_session_level(dimensions),
        "dimensions": dimensions,
        "counts": dict(snapshot.counts),
        "compatibility_key": snapshot.compatibility_key,
        "contract_version": REPORT_CONTRACT,
    }
    if snapshot.candidate_reflection is not None:
        report["candidate_reflection"] = dict(snapshot.candidate_reflection)
    return ConversationalReportSnapshot(report, "completed")


async def run_conversational_report(
    claim: ReportBuildClaim,
    repository: ReportRepository,
) -> None:
    """Build and publish a report through the claim's matching fence."""

    snapshot = await repository.load_report_input_snapshot(
        claim.session_id, claim.activity_version
    )
    if snapshot is None:
        return
    deterministic = build_conversational_report(snapshot)
    if claim.build_reason in {
        "transcript_deletion_rebuild",
        "reflection_update_rebuild",
    }:
        await repository.finalise_completed_session_report_rebuild(
            claim, deterministic.persisted_json(), deterministic.report_state
        )
    else:
        await repository.finalise_conversational_report(
            claim, deterministic.persisted_json(), deterministic.report_state
        )
