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


class DebriefSourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["question_bank_item"]
    id: str = Field(min_length=1)


class DebriefQuestionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=200)
    source_ref: DebriefSourceRef | None = None
    asked: bool = False
    rating: int | None = Field(default=None, ge=1, le=5)
    story_id: str | None = None
    note: str | None = Field(default=None, max_length=200)


class SaveDebriefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)
    overall: int = Field(ge=1, le=5)
    expectation: Literal["yes", "unsure", "no"] | None = None
    questions: list[DebriefQuestionWrite] = Field(default_factory=list, max_length=20)
    went_well: str | None = Field(default=None, max_length=1_000)
    do_differently: str | None = Field(default=None, max_length=1_000)
    notes_text: str | None = Field(default=None, max_length=2_500)


class SkipDebriefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)


class DebriefQuestionRead(BaseModel):
    id: str
    text: str
    source_ref: dict[str, str] | None = None
    asked: bool
    rating: int | None = None
    story_id: str | None = None
    note: str | None = None


class DebriefReadResponse(BaseModel):
    round_id: str
    application_id: str
    round_status: str | None = None
    scheduled_at: str | None = None
    duration_minutes: int | None = None
    status: Literal["due", "draft", "saved", "skipped"]
    version: int
    overall: int | None = None
    expectation: Literal["yes", "unsure", "no"] | None = None
    questions: list[DebriefQuestionRead] = Field(default_factory=list)
    went_well: str | None = None
    do_differently: str | None = None
    notes_text: str | None = None
    questions_added: int = 0


class ReadinessNextActionRead(BaseModel):
    application_id: str
    round_id: str
    action: str
    reason: str
    urgency: str
    kind: str
