"""R5's versioned, reference-only Job Scoring task contract."""

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


_REFERENCE_PATTERN = r"^[a-z0-9][a-z0-9._:-]*$"


class JobScoreInput(BaseModel):
    """References to existing product data; no job or candidate content is copied."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_ref: str = Field(min_length=1, max_length=256, pattern=_REFERENCE_PATTERN)
    profile_ref: str = Field(min_length=1, max_length=256, pattern=_REFERENCE_PATTERN)
    event_ref: str = Field(min_length=1, max_length=256, pattern=_REFERENCE_PATTERN)


class JobScoreOutput(BaseModel):
    """Existing durable JobScore semantics in the runtime task vocabulary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    skill_match: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    experience_match: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    rate_match: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    location_match: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    overall_score: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    reasoning: str
    keyword_matches: tuple[str, ...] = ()
    keyword_misses: tuple[str, ...] = ()
    fit_reasoning: str | None = None
    strengths: tuple[str, ...] = ()
    score_gaps: tuple[str, ...] = ()
    scoring_method: str


JOB_SCORE_V1 = TaskSpec(
    task_id="job.score",
    version=1,
    input_model=JobScoreInput,
    output_model=JobScoreOutput,
    context_requirements=(
        ContextRequirement(capability="candidate.profile_summary"),
        ContextRequirement(capability="candidate.resume_text", required=False),
        ContextRequirement(capability="job.description"),
        ContextRequirement(capability="job.requirements"),
    ),
    model_requirements=ModelCapabilityRequirements(),
    risk_class=RiskClass.MEDIUM,
    validators=("job_score.schema", "job_score.normalization"),
    evaluation_policy=EvaluationPolicy(max_evaluations=2, max_repairs=0),
    execution_strategy=ExecutionStrategy.FALLBACK_ON_FAILURE,
    workflow_policy=WorkflowPolicy(max_attempts=2),
)
