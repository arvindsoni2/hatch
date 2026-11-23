"""Coverage DTOs shared by the Phase 2 readiness services and routers."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Sequence

from ..coach_conversational_contracts import REPORT_CONTRACT

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


FocusStatus = Literal["active", "paused", "achieved", "archived"]
CriterionKind = Literal["level", "practice"]
CriterionStatus = Literal["not_started", "in_progress", "met", "no_evidence_yet"]


@dataclass(frozen=True)
class FocusGroup:
    role_family: str
    interview_type: str
    contract_version: str = REPORT_CONTRACT


@dataclass(frozen=True)
class FocusCriterion:
    kind: CriterionKind
    count: int = 1


@dataclass(frozen=True)
class CriterionRead:
    kind: CriterionKind
    label: str
    status: CriterionStatus
    completed: int
    target: int


@dataclass(frozen=True)
class PlanFocusInput:
    focus_id: str
    title: str
    status: FocusStatus
    group: FocusGroup | None
    created_at: datetime
    all_criteria_met: bool
    latest_difficulty: str | None = None


@dataclass(frozen=True)
class TargetRound:
    round_id: str
    scheduled_at: datetime
    application_id: str | None = None


@dataclass(frozen=True)
class PlanItem:
    id: str
    type: Literal["practice_session", "story_work", "review_answer"]
    title: str
    minutes: int
    status: Literal["todo", "done", "skipped"] = "todo"
    group: FocusGroup | None = None
    difficulty: str | None = None
    focus_area_ids: tuple[str, ...] = ()
    due_at: datetime | None = None
    story_competency: str | None = None
    question_id: str | None = None
    auto: bool = False
    completed_at: datetime | None = None


@dataclass(frozen=True)
class PlanDraft:
    items: tuple[PlanItem, ...]
    unallocated_minutes: int


class PlanError(Exception):
    """A safe plan error code from spec §12."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class SourceRef:
    kind: str
    source_id: str
    version: str


@dataclass(frozen=True)
class GenerationRequest:
    task_id: str
    kind: str
    cache_key: str
    input_fingerprint: str
    sources: tuple[SourceRef, ...]
    params: Mapping[str, str] | None = None


@dataclass(frozen=True)
class ValidatedOutput:
    text_json: Mapping[str, Any]
    model_identity: str
    prompt_version: str


@dataclass(frozen=True)
class GenerationOutcome:
    status: Literal["succeeded", "fenced"]
    derived_text_id: str | None = None


def input_fingerprint(
    task_id: str,
    sources: Sequence[SourceRef],
    params: Mapping[str, str] | None = None,
) -> str:
    payload = {
        "task": task_id,
        "params": dict(sorted((params or {}).items())),
        "sources": sorted(
            [[source.kind, source.source_id, source.version] for source in sources]
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


async def finalise_generation(
    session, request: GenerationRequest, output: ValidatedOutput, now
) -> GenerationOutcome:
    from sqlalchemy import delete

    from app.models.application import InterviewRound
    from app.models.coach_readiness import CoachDerivedSource, CoachDerivedText
    from app.models.coach_session import InterviewSession
    from app.models.question_bank import QuestionBankItem
    from app.models.story import Story

    # The first statement is a write so SQLite takes the write lock before any
    # source is read. A concurrent source deletion cannot commit in between.
    await session.execute(
        delete(CoachDerivedText).where(CoachDerivedText.cache_key == request.cache_key)
    )

    current: list[SourceRef] = []
    for ref in request.sources:
        if ref.kind == "coach_session":
            row = await session.get(InterviewSession, ref.source_id)
            if (
                row is None
                or row.deletion_state != "not_requested"
                or str(row.activity_version) != ref.version
            ):
                return GenerationOutcome("fenced")
            current.append(SourceRef(ref.kind, ref.source_id, str(row.activity_version)))
        elif ref.kind == "story":
            row = await session.get(Story, ref.source_id)
            if row is None or not row.is_active or str(row.version) != ref.version:
                return GenerationOutcome("fenced")
            current.append(SourceRef(ref.kind, ref.source_id, str(row.version)))
        elif ref.kind == "question_bank_item":
            row = await session.get(QuestionBankItem, ref.source_id)
            if row is None or row.archived_at is not None:
                return GenerationOutcome("fenced")
            version = row.updated_at.isoformat() if row.updated_at else ""
            if version != ref.version:
                return GenerationOutcome("fenced")
            current.append(SourceRef(ref.kind, ref.source_id, version))
        elif ref.kind == "interview_round":
            row = await session.get(InterviewRound, ref.source_id)
            if row is None or row.status == "cancelled":
                return GenerationOutcome("fenced")
            version = row.updated_at.isoformat() if row.updated_at else ""
            if version != ref.version:
                return GenerationOutcome("fenced")
            current.append(SourceRef(ref.kind, ref.source_id, version))
        else:
            return GenerationOutcome("fenced")

    if input_fingerprint(request.task_id, current, request.params) != request.input_fingerprint:
        return GenerationOutcome("fenced")

    text = CoachDerivedText(
        kind=request.kind,
        cache_key=request.cache_key,
        text_json=dict(output.text_json),
        model_identity=output.model_identity,
        prompt_version=output.prompt_version,
        created_at=now.replace(tzinfo=None),
    )
    session.add(text)
    await session.flush()
    for ref in request.sources:
        session.add(
            CoachDerivedSource(
                derived_text_id=text.id,
                source_kind=ref.kind,
                source_id=ref.source_id,
                source_version=ref.version,
            )
        )
    await session.flush()
    return GenerationOutcome("succeeded", text.id)
