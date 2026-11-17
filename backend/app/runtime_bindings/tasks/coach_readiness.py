"""Versioned, reference-only Coach readiness task contracts (spec §10)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.runtime.context import ContextRequirement
from app.runtime.contracts import (
    EvaluationPolicy,
    ExecutionStrategy,
    ModelCapabilityRequirements,
    RiskClass,
    TaskSpec,
    WorkflowPolicy,
)

_REF = r"^[a-z0-9][a-z0-9._:-]*$"


class ExplainInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    pattern_ref: str = Field(min_length=1, max_length=256, pattern=_REF)
    excerpt_refs: tuple[str, ...] = Field(default=(), max_length=2)


class ExplainOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tips: tuple[str, ...] = Field(min_length=1, max_length=3)


class BriefEnhanceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    round_ref: str = Field(min_length=1, max_length=256, pattern=_REF)
    enhancement_fingerprint: str = Field(min_length=1, max_length=128)
    story_refs: tuple[str, ...] = Field(default=(), max_length=3)
    pattern_refs: tuple[str, ...] = Field(default=(), max_length=2)


class TalkingPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    story_id: str
    text: str


class WatchOutTip(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    fingerprint: str
    text: str


class BriefEnhanceOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    talking_points: tuple[TalkingPoint, ...] = ()
    watch_outs: tuple[WatchOutTip, ...] = ()


class PlanWordingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    plan_ref: str = Field(min_length=1, max_length=256, pattern=_REF)
    item_refs: tuple[str, ...] = ()


class PlanWordingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    titles: tuple[str, ...] = ()


class DebriefExtractInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    debrief_ref: str = Field(min_length=1, max_length=256, pattern=_REF)


class DebriefExtractOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    questions: tuple[str, ...] = Field(default=(), max_length=12)


class CompetencyExtractInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    job_ref: str = Field(min_length=1, max_length=256, pattern=_REF)
    description_hash: str = Field(min_length=1, max_length=128)


class CompetencyExtractOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    competencies: tuple[str, ...] = Field(default=(), max_length=4)


def _spec(task_id, input_model, output_model, tier: str) -> TaskSpec:
    return TaskSpec(
        task_id=task_id,
        version=1,
        input_model=input_model,
        output_model=output_model,
        context_requirements=(
            ContextRequirement(capability="coach.readiness.evidence"),
        ),
        model_requirements=ModelCapabilityRequirements(),
        risk_class=RiskClass.LOW,
        validators=("coach_readiness.grounding",),
        evaluation_policy=EvaluationPolicy(max_evaluations=2, max_repairs=1),
        execution_strategy=ExecutionStrategy.FALLBACK_ON_FAILURE,
        workflow_policy=WorkflowPolicy(max_attempts=1),
    )


COACH_READINESS_EXPLAIN_V1 = _spec("coach.readiness.explain", ExplainInput, ExplainOutput, "S")
COACH_READINESS_BRIEF_ENHANCE_V1 = _spec("coach.readiness.brief_enhance", BriefEnhanceInput, BriefEnhanceOutput, "S")
COACH_READINESS_PLAN_WORDING_V1 = _spec("coach.readiness.plan_wording", PlanWordingInput, PlanWordingOutput, "S")
COACH_READINESS_DEBRIEF_EXTRACT_V1 = _spec("coach.readiness.debrief_extract", DebriefExtractInput, DebriefExtractOutput, "T")
COACH_READINESS_COMPETENCY_EXTRACT_V1 = _spec("coach.readiness.competency_extract", CompetencyExtractInput, CompetencyExtractOutput, "T")

__all__ = [
    "COACH_READINESS_BRIEF_ENHANCE_V1",
    "COACH_READINESS_COMPETENCY_EXTRACT_V1",
    "COACH_READINESS_DEBRIEF_EXTRACT_V1",
    "COACH_READINESS_EXPLAIN_V1",
    "COACH_READINESS_PLAN_WORDING_V1",
]
