"""Deterministic compatibility-grouped progress for conversational Coach."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from ..schemas.coach_conversation import ConversationalProgressRead
from .coach_conversational_report import LEVEL_TO_ORDINAL, Level
from .coach_conversational_contracts import CONTENT_DIMENSIONS, PROGRESS_CONTRACT

Trend = Literal[
    "improving",
    "stable",
    "mixed",
    "declining",
    "not_enough_evidence",
]


@dataclass(frozen=True)
class ProgressSelector:
    mode: Literal["exact", "filtered"]
    application_id: str | None = None
    compatibility_key: str | None = None
    role_family: str | None = None
    role_level: str | None = None
    interview_type: str | None = None

    def __post_init__(self) -> None:
        filters = (
            self.application_id,
            self.role_family,
            self.role_level,
            self.interview_type,
        )
        if self.mode == "exact":
            if not self.compatibility_key or any(value is not None for value in filters):
                raise ValueError("exact selector accepts only compatibility_key")
        elif self.mode == "filtered":
            if self.compatibility_key is not None or not any(filters):
                raise ValueError("filtered selector requires a broad filter and no exact key")
        else:
            raise ValueError("unsupported progress selector mode")


@dataclass(frozen=True)
class ProgressSnapshot:
    session_id: str
    compatibility_key: str
    activity_version: int
    completed_at: datetime
    session_level: Level
    dimensions: Mapping[str, Level]
    application_id: str | None = None
    company_name: str | None = None
    role_title: str | None = None
    role_family: str | None = None
    role_level: str | None = None
    interview_type: str | None = None
    strengths: tuple[Mapping[str, object], ...] = ()
    priorities: tuple[Mapping[str, object], ...] = ()
    evidence_review_items: tuple[Mapping[str, object], ...] = ()


class ProgressSnapshotRepository(Protocol):
    async def load_progress_snapshots(
        self, selector: ProgressSelector
    ) -> Sequence[ProgressSnapshot]: ...


def derive_trend(levels: Sequence[Level | str]) -> Trend:
    """Derive a named-level trend from the latest three assessed reports."""

    assessed = [
        LEVEL_TO_ORDINAL[level]
        for level in levels
        if level in LEVEL_TO_ORDINAL and level != "not_assessed"
    ][-3:]
    if len(assessed) < 2:
        return "not_enough_evidence"
    if len(assessed) == 3 and (
        (assessed[1] - assessed[0]) * (assessed[2] - assessed[1]) < 0
    ):
        return "mixed"
    if assessed[-1] > assessed[-2]:
        return "improving"
    if assessed[-1] < assessed[-2]:
        return "declining"
    return "stable"


def _matches(snapshot: ProgressSnapshot, selector: ProgressSelector) -> bool:
    if selector.mode == "exact":
        return snapshot.compatibility_key == selector.compatibility_key
    return all(
        getattr(snapshot, field_name) == value
        for field_name, value in (
            ("application_id", selector.application_id),
            ("role_family", selector.role_family),
            ("role_level", selector.role_level),
            ("interview_type", selector.interview_type),
        )
        if value is not None
    )


def _filters(selector: ProgressSelector) -> dict[str, str]:
    return {
        field_name: value
        for field_name, value in (
            ("application_id", selector.application_id),
            ("compatibility_key", selector.compatibility_key),
            ("role_family", selector.role_family),
            ("role_level", selector.role_level),
            ("interview_type", selector.interview_type),
        )
        if value is not None
    }


def get_progress(
    selector: ProgressSelector,
    group_limit: int,
    *,
    snapshots: Sequence[ProgressSnapshot],
) -> ConversationalProgressRead:
    """Group visible report snapshots without merging incompatible rubrics."""

    if not 1 <= group_limit <= 100:
        raise ValueError("group limit must be between 1 and 100")
    selected = [snapshot for snapshot in snapshots if _matches(snapshot, selector)]
    grouped: dict[str, list[ProgressSnapshot]] = defaultdict(list)
    for snapshot in selected:
        grouped[snapshot.compatibility_key].append(snapshot)

    group_rows: list[dict[str, object]] = []
    for compatibility_key, members in grouped.items():
        ordered = sorted(
            members,
            key=lambda item: (item.completed_at, item.session_id),
        )
        latest = ordered[-1]
        assessed = {
            dimension: [
                item.dimensions[dimension]
                for item in ordered
                if item.dimensions.get(dimension) in LEVEL_TO_ORDINAL
                and item.dimensions[dimension] != "not_assessed"
            ][-3:]
            for dimension in CONTENT_DIMENSIONS
        }
        group_rows.append(
            {
                "compatibility_key": compatibility_key,
                "context": {
                    name: getattr(latest, name)
                    for name in (
                        "application_id", "company_name", "role_title", "role_family",
                        "role_level", "interview_type",
                    )
                },
                "current_levels": {
                    name: levels[-1] if levels else "not_assessed"
                    for name, levels in assessed.items()
                },
                "previous_levels": {
                    name: levels[-2] if len(levels) >= 2 else "not_assessed"
                    for name, levels in assessed.items()
                },
                "trends": {name: derive_trend(levels) for name, levels in assessed.items()},
                "strongest_areas": list(latest.strengths),
                "priority_areas": list(latest.priorities),
                "evidence_review_items": list(latest.evidence_review_items),
                "sessions": [
                    {
                        "session_id": item.session_id,
                        "activity_version": item.activity_version,
                        "completed_at": item.completed_at.isoformat(),
                        "session_level": item.session_level,
                        "dimensions": {
                            name: item.dimensions.get(name, "not_assessed")
                            for name in CONTENT_DIMENSIONS
                        },
                    }
                    for item in ordered
                ],
            }
        )

    group_rows.sort(key=lambda item: item["compatibility_key"])
    group_rows.sort(key=lambda item: item["sessions"][-1]["completed_at"], reverse=True)
    return ConversationalProgressRead(
        selector_mode=selector.mode,
        applied_filters=_filters(selector),
        group_limit=group_limit,
        total_groups=len(group_rows),
        returned_groups=min(len(group_rows), group_limit),
        groups_truncated=len(group_rows) > group_limit,
        groups=group_rows[:group_limit],
        contract_version=PROGRESS_CONTRACT,
    )


class ConversationalProgressService:
    """Database adapter for the pure progress grouping function."""

    def __init__(self, repository: ProgressSnapshotRepository) -> None:
        self.repository = repository

    async def get_progress(
        self, selector: ProgressSelector, group_limit: int
    ) -> ConversationalProgressRead:
        snapshots = await self.repository.load_progress_snapshots(selector)
        return get_progress(selector, group_limit, snapshots=snapshots)
