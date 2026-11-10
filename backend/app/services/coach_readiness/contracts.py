"""Coverage DTOs shared by the Phase 2 readiness services and routers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Sequence

CoverageStatus = Literal["covered", "thin", "gap"]
CoverageAction = Literal["use", "strengthen", "draft"]


@dataclass(frozen=True)
class Competency:
    text: str
    match_key: str


@dataclass(frozen=True)
class CoverageOverride:
    original: str
    replacement: str | None = None
    hidden: bool = False


@dataclass(frozen=True)
class CoverageStory:
    story_id: str
    title: str
    score: float
    has_metric: bool


@dataclass(frozen=True)
class CompetencyCoverage:
    competency: str
    status: CoverageStatus
    action: CoverageAction
    stories: tuple[CoverageStory, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CoverageMap:
    application_id: str
    competencies: tuple[CompetencyCoverage, ...] = field(default_factory=tuple)

    @property
    def covered_count(self) -> int:
        return sum(item.status == "covered" for item in self.competencies)

    @property
    def thin_count(self) -> int:
        return sum(item.status == "thin" for item in self.competencies)

    @property
    def gap_count(self) -> int:
        return sum(item.status == "gap" for item in self.competencies)


@dataclass(frozen=True)
class CoverageGap:
    competency: str
    application_count: int


@dataclass(frozen=True)
class CoverageOverview:
    gaps: tuple[CoverageGap, ...] = field(default_factory=tuple)


DebriefStatus = Literal["due", "draft", "saved", "skipped"]


@dataclass(frozen=True)
class DebriefQuestion:
    id: str
    text: str
    source_ref: dict[str, str] | None = None
    asked: bool = False
    rating: int | None = None
    story_id: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class SaveDebriefCommand:
    expected_version: int
    overall: int
    expectation: str | None = None
    questions: Sequence[DebriefQuestion] = field(default_factory=tuple)
    went_well: str | None = None
    do_differently: str | None = None
    notes_text: str | None = None


@dataclass(frozen=True)
class DebriefRead:
    status: DebriefStatus
    version: int
    overall: int | None = None
    expectation: str | None = None
    questions: Sequence[DebriefQuestion] = field(default_factory=tuple)
    went_well: str | None = None
    do_differently: str | None = None
    notes_text: str | None = None
    round_id: str = ""
    application_id: str = ""
    round_status: str | None = None
    scheduled_at: datetime | None = None
    duration_minutes: int | None = None
    questions_added: int = 0


class ReadinessError(Exception):
    """A safe readiness error code from spec §12."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


PatternKind = Literal["focus", "strength", "mixed", "forming"]
PatternTrendLabel = Literal[
    "improving", "easier_difficulty", "getting_weaker", "harder_difficulty"
]


@dataclass(frozen=True)
class PatternGroup:
    role_family: str
    interview_type: str
    contract_version: str


@dataclass(frozen=True)
class SupportingSession:
    session_id: str
    completed_at: datetime
    level: str
    difficulty: str | None
    role_level: str | None


@dataclass(frozen=True)
class Pattern:
    fingerprint: str
    group: PatternGroup
    dimension: str
    kind: PatternKind
    trend: str
    trend_label: PatternTrendLabel | None
    supporting: tuple[SupportingSession, ...]
    stale: bool
    dismissed: bool
    seen_again: bool = False


@dataclass(frozen=True)
class PatternPolicy:
    window_days: int = 90
    max_sessions: int = 3


@dataclass(frozen=True)
class WhyExcerpt:
    session_id: str
    completed_at: datetime
    text: str


@dataclass(frozen=True)
class PatternWhy:
    pattern: Pattern
    excerpts: tuple[WhyExcerpt, ...] = field(default_factory=tuple)
