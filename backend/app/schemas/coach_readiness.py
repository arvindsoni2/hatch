"""HTTP contracts for Coach readiness coverage routes."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CoverageStatus = Literal["covered", "thin", "gap"]
CoverageAction = Literal["use", "strengthen", "draft"]


class CoverageStoryRead(BaseModel):
    story_id: str
    title: str
    score: float
    has_metric: bool


class CompetencyCoverageRead(BaseModel):
    competency: str
    status: CoverageStatus
    action: CoverageAction
    stories: list[CoverageStoryRead] = Field(default_factory=list)


class CoverageMapRead(BaseModel):
    application_id: str
    covered_count: int
    thin_count: int
    gap_count: int
    competencies: list[CompetencyCoverageRead] = Field(default_factory=list)


class CoverageGapRead(BaseModel):
    competency: str
    application_count: int


class CoverageOverviewRead(BaseModel):
    gaps: list[CoverageGapRead] = Field(default_factory=list)


class CompetencyOverrideWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original: str = Field(min_length=1, max_length=200)
    replacement: str | None = Field(default=None, max_length=200)
    hidden: bool = False


class CoverageOverridesWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overrides: list[CompetencyOverrideWrite] = Field(default_factory=list, max_length=100)
