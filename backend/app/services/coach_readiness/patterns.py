"""Pattern derivation and the deterministic Why panel (spec §7.1, §7.7)."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta

from app.services.coach_conversational_contracts import CONTENT_DIMENSIONS
from app.services.coach_conversational_progress import ProgressSnapshot, derive_trend

from .contracts import (
    Pattern,
    PatternGroup,
    PatternPolicy,
    PatternWhy,
    SupportingSession,
    WhyExcerpt,
)

WEAK_LEVELS = frozenset({"needs_work", "developing"})
STRONG_LEVELS = frozenset({"interview_ready", "strong"})
DIFFICULTY_ORDER = {"supportive": 0, "realistic": 1, "challenging": 2}
UNSPECIFIED = "unspecified"


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _group_of(snapshot: ProgressSnapshot) -> PatternGroup:
    return PatternGroup(
        role_family=snapshot.role_family or UNSPECIFIED,
        interview_type=snapshot.interview_type or UNSPECIFIED,
        contract_version=snapshot.evaluation_contract_version,
    )


def _fingerprint(group: PatternGroup, dimension: str, kind: str, ids: Sequence[str]) -> str:
    payload = "\x1f".join(
        [
            group.role_family,
            group.interview_type,
            group.contract_version,
            dimension,
            kind,
            *sorted(ids),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _unique_sessions(snapshots: Sequence[ProgressSnapshot]) -> list[ProgressSnapshot]:
    """Count distinct sessions: a retried attempt never becomes a second data point."""
    latest: dict[str, ProgressSnapshot] = {}
    for snapshot in snapshots:
        current = latest.get(snapshot.session_id)
        if current is None or (snapshot.completed_at, snapshot.activity_version) > (
            current.completed_at,
            current.activity_version,
        ):
            latest[snapshot.session_id] = snapshot
    return list(latest.values())


def _kind(levels: Sequence[str]) -> str:
    if len(levels) == 1:
        return "forming"
    weak = sum(level in WEAK_LEVELS for level in levels)
    strong = sum(level in STRONG_LEVELS for level in levels)
    if weak >= 2 and strong == 0:
        return "focus"
    if strong >= 2 and weak == 0:
        return "strength"
    return "mixed"


def _trend_label(trend: str, supporting: Sequence[SupportingSession]) -> str | None:
    if trend not in {"improving", "declining"} or len(supporting) < 2:
        return None
    oldest = DIFFICULTY_ORDER.get(supporting[0].difficulty or "")
    newest = DIFFICULTY_ORDER.get(supporting[-1].difficulty or "")
    if oldest is None or newest is None:
        return None
    if trend == "improving":
        return "improving" if newest >= oldest else "easier_difficulty"
    return "getting_weaker" if newest <= oldest else "harder_difficulty"


def derive_patterns(
    snapshots: Sequence[ProgressSnapshot],
    dismissed: frozenset[str],
    policy: PatternPolicy,
    now: datetime,
) -> tuple[Pattern, ...]:
    if policy.window_days < 1 or policy.max_sessions < 1:
        raise ValueError("invalid pattern policy")
    cutoff = _utc(now) - timedelta(days=policy.window_days)
    grouped: dict[tuple[str, str, str], list[ProgressSnapshot]] = {}
    for snapshot in _unique_sessions(snapshots):
        group = _group_of(snapshot)
        grouped.setdefault(
            (group.role_family, group.interview_type, group.contract_version), []
        ).append(snapshot)

    patterns: list[Pattern] = []
    for key in sorted(grouped):
        group = PatternGroup(
            role_family=key[0], interview_type=key[1], contract_version=key[2]
        )
        members = sorted(
            grouped[key],
            key=lambda item: (item.completed_at, item.session_id),
            reverse=True,
        )
        for dimension in CONTENT_DIMENSIONS:
            assessed = [
                item
                for item in members
                if item.dimensions.get(dimension)
                and item.dimensions[dimension] != "not_assessed"
            ][: policy.max_sessions]
            if not assessed:
                continue
            supporting = tuple(
                SupportingSession(
                    session_id=item.session_id,
                    completed_at=item.completed_at,
                    level=item.dimensions[dimension],
                    difficulty=item.difficulty,
                    role_level=item.role_level,
                )
                for item in sorted(
                    assessed, key=lambda item: (item.completed_at, item.session_id)
                )
            )
            levels = [item.level for item in supporting]
            kind = _kind(levels)
            trend = derive_trend(levels)
            fingerprint = _fingerprint(
                group, dimension, kind, [item.session_id for item in supporting]
            )
            patterns.append(
                Pattern(
                    fingerprint=fingerprint,
                    group=group,
                    dimension=dimension,
                    kind=kind,
                    trend=trend,
                    trend_label=_trend_label(trend, supporting),
                    supporting=supporting,
                    stale=_utc(supporting[-1].completed_at) < cutoff,
                    dismissed=fingerprint in dismissed,
                )
            )
    return tuple(patterns)


def explain_pattern(
    pattern: Pattern, snapshots: Sequence[ProgressSnapshot]
) -> PatternWhy | None:
    """Why? uses only stored report excerpts; no model and no invented text."""
    if pattern.stale:
        return None
    by_session = {item.session_id: item for item in _unique_sessions(snapshots)}
    excerpts: list[WhyExcerpt] = []
    for supporting in reversed(pattern.supporting):
        snapshot = by_session.get(supporting.session_id)
        if snapshot is None:
            continue
        for item in snapshot.priorities:
            if not isinstance(item, Mapping):
                continue
            if item.get("dimension") != pattern.dimension:
                continue
            text = item.get("next_action")
            if not isinstance(text, str) or not text.strip():
                continue
            excerpts.append(
                WhyExcerpt(
                    session_id=supporting.session_id,
                    completed_at=supporting.completed_at,
                    text=text.strip(),
                )
            )
            if len(excerpts) == 2:
                return PatternWhy(pattern=pattern, excerpts=tuple(excerpts))
    return PatternWhy(pattern=pattern, excerpts=tuple(excerpts))
