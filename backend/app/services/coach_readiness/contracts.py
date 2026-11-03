"""Coverage DTOs shared by the Phase 2 readiness services and routers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

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
