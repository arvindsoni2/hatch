"""Versioned, deterministic contract for CV tailoring runtime work."""

from __future__ import annotations

import re
from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from app.runtime.context import ContextRequirement
from app.runtime.contracts import (
    EvaluationPolicy,
    ExecutionResultCode,
    ExecutionStrategy,
    ModelCapabilityRequirements,
    RiskClass,
    TaskSpec,
    WorkflowPolicy,
)
from app.schemas.tailor import TailoredCVResult


_REFERENCE_PATTERN = r"^[a-z0-9][a-z0-9._:-]*$"
_SPACE = re.compile(r"\s+")


class CVTailorInput(BaseModel):
    """Opaque product references only; CV/JD contents stay in product memory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    application_ref: str = Field(
        min_length=1, max_length=256, pattern=_REFERENCE_PATTERN
    )
    job_ref: str = Field(min_length=1, max_length=256, pattern=_REFERENCE_PATTERN)
    variant: str = Field(default="A", min_length=1, max_length=32)
    request_ref: str = Field(
        default="request:legacy",
        min_length=1,
        max_length=256,
        pattern=_REFERENCE_PATTERN,
    )
    delivery_ref: str = Field(
        default="delivery:direct", max_length=256, pattern=_REFERENCE_PATTERN
    )
    input_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class CVTailorInvocation(CVTailorInput):
    """Gateway-only request including its router-authorized model identity."""

    model_id: str = Field(min_length=1, max_length=128, pattern=_REFERENCE_PATTERN)
    provider: str = Field(min_length=1, max_length=128, pattern=_REFERENCE_PATTERN)


class CVTailorOutput(BaseModel):
    """Validated CV content plus an opaque artifact contract."""

    model_config = ConfigDict(extra="forbid")

    tailored_cv: TailoredCVResult
    artifact_ref: str | None = Field(
        default=None, min_length=1, max_length=256, pattern=_REFERENCE_PATTERN
    )
    artifact_bytes: int | None = Field(default=None, ge=1)
    artifact_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    section_count: int | None = Field(default=None, ge=1)
    # A transient, in-memory allowlist of source-supported statements. It is
    # intentionally not persisted in runtime/shadow metadata.
    source_claims: tuple[str, ...] = Field(default=(), exclude=True)


CV_TAILOR_V1 = TaskSpec(
    task_id="cv.tailor",
    version=1,
    input_model=CVTailorInput,
    output_model=CVTailorOutput,
    context_requirements=(
        ContextRequirement(capability="candidate.verified_experience"),
        ContextRequirement(capability="candidate.achievements"),
        ContextRequirement(capability="candidate.skills"),
        ContextRequirement(capability="candidate.resume_text"),
        ContextRequirement(capability="job.requirements"),
        ContextRequirement(capability="job.description"),
    ),
    model_requirements=ModelCapabilityRequirements(),
    risk_class=RiskClass.MEDIUM,
    validators=(
        "cv_tailor.schema",
        "cv_tailor.required_sections",
        "cv_tailor.artifact_contract",
        "cv_tailor.source_supported_claims",
    ),
    evaluation_policy=EvaluationPolicy(max_evaluations=2, max_repairs=1),
    execution_strategy=ExecutionStrategy.FALLBACK_ON_FAILURE,
    workflow_policy=WorkflowPolicy(max_attempts=2),
)


class CVTailorValidationResult(BaseModel):
    """Content-free deterministic decision used before any model evaluator."""

    model_config = ConfigDict(frozen=True)

    code: ExecutionResultCode
    reason_code: str


def _normalise(value: str) -> str:
    return _SPACE.sub(" ", value.strip().casefold())


def _claims(tailored: TailoredCVResult) -> Iterable[str]:
    yield tailored.summary
    for experience in tailored.experience:
        yield from experience.achievements


def validate_cv_tailor_output(
    output: object, *, source_claims: Iterable[str] | None = None
) -> CVTailorValidationResult:
    """Validate schema, sections, artifact and grounding in fixed order."""

    try:
        typed = CVTailorOutput.model_validate(output)
    except Exception:
        return CVTailorValidationResult(
            code=ExecutionResultCode.VALIDATION_FAILURE,
            reason_code="cv_tailor_schema_invalid",
        )
    cv = typed.tailored_cv
    if (
        not cv.summary.strip()
        or not cv.skills
        or not cv.experience
        or any(not isinstance(g, dict) or not g.get("items") for g in cv.skills)
        or any(
            not e.role.strip()
            or not e.company.strip()
            or not e.period.strip()
            or not e.achievements
            or any(not a.strip() for a in e.achievements)
            for e in cv.experience
        )
    ):
        return CVTailorValidationResult(
            code=ExecutionResultCode.VALIDATION_FAILURE,
            reason_code="cv_tailor_required_section_missing",
        )
    if (typed.artifact_ref is None) != (typed.artifact_bytes is None):
        return CVTailorValidationResult(
            code=ExecutionResultCode.VALIDATION_FAILURE,
            reason_code="cv_tailor_artifact_contract_invalid",
        )
    evidence = {_normalise(claim) for claim in (source_claims or ()) if claim.strip()}
    # Model-produced provenance IDs are not statement-level evidence.  The
    # caller must provide a product-owned allowlist built from the source CV;
    # without it, no rendered summary or achievement is eligible to commit.
    if not evidence or any(_normalise(claim) not in evidence for claim in _claims(cv)):
        return CVTailorValidationResult(
            code=ExecutionResultCode.VALIDATION_FAILURE,
            reason_code="cv_tailor_unsupported_claim",
        )
    return CVTailorValidationResult(
        code=ExecutionResultCode.SUCCESS,
        reason_code="cv_tailor_valid",
    )
