"""Deterministic compatibility-grouped progress for conversational Coach."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from ..schemas.coach_conversation import ConversationalProgressRead
from .coach_conversational_report import LEVEL_TO_ORDINAL, Level
from .coach_conversational_contracts import PROGRESS_CONTRACT

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
    session_id: str | None = None
    application_id: str | None = None
    compatibility_key: str | None = None
    company_name: str | None = None
    role_title: str | None = None

    def __post_init__(self) -> None:
        filters = (
            self.application_id,
            self.compatibility_key,
            self.company_name,
            self.role_title,
        )
        if self.mode == "exact":
            if self.session_id is None or any(value is not None for value in filters):
                raise ValueError("exact selector accepts only session_id")
        elif self.mode == "filtered":
            if self.session_id is not None:
                raise ValueError("filtered selector cannot include session_id")
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
        return snapshot.session_id == selector.session_id
    return all(
        getattr(snapshot, field_name) == value
        for field_name, value in (
            ("application_id", selector.application_id),
            ("compatibility_key", selector.compatibility_key),
            ("company_name", selector.company_name),
            ("role_title", selector.role_title),
        )
        if value is not None
    )


def _filters(selector: ProgressSelector) -> dict[str, str]:
    return {
        field_name: value
        for field_name, value in (
            ("session_id", selector.session_id),
            ("application_id", selector.application_id),
            ("compatibility_key", selector.compatibility_key),
            ("company_name", selector.company_name),
            ("role_title", selector.role_title),
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
        group_rows.append(
            {
                "compatibility_key": compatibility_key,
                "session_count": len(ordered),
                "latest_session_id": ordered[-1].session_id,
                "latest_activity_version": ordered[-1].activity_version,
                "latest_session_level": ordered[-1].session_level,
                "trend": derive_trend([item.session_level for item in ordered]),
                "sessions": [
                    {
                        "session_id": item.session_id,
                        "activity_version": item.activity_version,
                        "completed_at": item.completed_at.isoformat(),
                        "session_level": item.session_level,
                        "dimensions": dict(item.dimensions),
                    }
                    for item in ordered
                ],
            }
        )

    group_rows.sort(
        key=lambda item: (
            item["sessions"][-1]["completed_at"],
            item["compatibility_key"],
        ),
        reverse=True,
    )
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
