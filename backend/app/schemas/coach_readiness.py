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


PatternKind = Literal["focus", "strength", "mixed", "forming"]
PatternTrendLabel = Literal[
    "improving", "easier_difficulty", "getting_weaker", "harder_difficulty"
]


class PatternSupportRead(BaseModel):
    session_id: str
    completed_at: str
    level: str
    difficulty: str | None = None
    role_level: str | None = None


class PatternGroupRead(BaseModel):
    role_family: str
    interview_type: str
    contract_version: str


class PatternRead(BaseModel):
    fingerprint: str
    group: PatternGroupRead
    dimension: str
    kind: PatternKind
    trend: str
    trend_label: PatternTrendLabel | None = None
    supporting: list[PatternSupportRead] = Field(default_factory=list)
    stale: bool = False
    dismissed: bool = False
    seen_again: bool = False


class PatternGroupSectionRead(BaseModel):
    role_family: str
    interview_type: str
    contract_version: str
    session_count: int
    patterns: list[PatternRead] = Field(default_factory=list)


class PatternListRead(BaseModel):
    groups: list[PatternGroupSectionRead] = Field(default_factory=list)
    include_stale: bool = False


class PatternWhyExcerptRead(BaseModel):
    session_id: str
    completed_at: str
    text: str


class PatternWhyRead(BaseModel):
    pattern: PatternRead
    excerpts: list[PatternWhyExcerptRead] = Field(default_factory=list)


FocusStatus = Literal["active", "paused", "achieved", "archived"]
CriterionKind = Literal["level", "practice"]
CriterionStatus = Literal["not_started", "in_progress", "met", "no_evidence_yet"]


class FocusGroupWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_family: str = Field(min_length=1, max_length=80)
    interview_type: str = Field(min_length=1, max_length=40)
    contract_version: str = Field(
        default="coach_conversational_report_v1", min_length=1, max_length=80
    )


class FocusGroupRead(FocusGroupWrite):
    pass


class FocusCriterionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: CriterionKind
    count: int | None = Field(default=None, ge=1, le=10)


class FocusCriterionRead(BaseModel):
    kind: CriterionKind
    label: str
    status: CriterionStatus
    completed: int
    target: int


class FocusAreaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=80)
    dimension: str = Field(min_length=1, max_length=32)
    group: FocusGroupWrite | None = None
    application_id: str | None = None
    criteria: list[FocusCriterionWrite] = Field(min_length=1, max_length=2)


class FocusAreaPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)
    title: str | None = Field(default=None, min_length=1, max_length=80)
    status: FocusStatus | None = None


class FocusAreaRead(BaseModel):
    id: str
    version: int
    status: FocusStatus
    active_slot: int | None = None
    title: str
    dimension: str
    group: FocusGroupRead | None = None
    application_id: str | None = None
    criteria: list[FocusCriterionRead] = Field(default_factory=list)
    every_criterion_met: bool = False
    created_at: str


class FocusAreaListRead(BaseModel):
    items: list[FocusAreaRead] = Field(default_factory=list)
    active_count: int = 0
    active_limit: int = 3


class PlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minutes: int = Field(default=30, ge=10, le=120)
    target_round_id: str | None = None


class PlanItemPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["done", "skipped", "todo"]


class PlanItemRead(BaseModel):
    id: str
    type: Literal["practice_session", "story_work", "review_answer"]
    title: str
    minutes: int
    status: Literal["todo", "done", "skipped"]
    group: FocusGroupRead | None = None
    focus_area_ids: list[str] = Field(default_factory=list)
    due_at: str | None = None
    auto: bool = False
    completed_at: str | None = None


class PlanRead(BaseModel):
    id: str
    version: int
    status: Literal[
        "draft", "active", "completed", "superseded", "expired", "discarded"
    ]
    minutes: int
    target_round_id: str | None = None
    items: list[PlanItemRead] = Field(default_factory=list)
    unallocated_minutes: int = 0
    done_count: int = 0
    total_count: int = 0
    started_at: str | None = None
    completed_at: str | None = None


class PlanListRead(BaseModel):
    active: PlanRead | None = None
    draft: PlanRead | None = None
