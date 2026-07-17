"""Typed, privacy-safe orchestration primitives for document-writing skills."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any, Literal

from ..schemas.tailor import (
    CoverLetterResult,
    JDAnalysisResult,
    TailoredCVResult,
)
from .writing_contracts import (
    EvidenceItem,
    PromptMetadata,
    ValidationIssue,
    ValidationResult,
    normalize_evidence_text,
)

REPAIR_PRIORITY = (
    "unsupported_numeric_token",
    "mutated_numeric_token",
    "missing_required_fields",
    "under_length",
    "over_length",
)


@dataclass(frozen=True)
class JobRequirement:
    id: str
    text: str
    source_path: str


@dataclass(frozen=True)
class EvidenceSelection:
    evidence: tuple[EvidenceItem, ...]

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return tuple(item.id for item in self.evidence)


@dataclass(frozen=True)
class CoverLetterContentPlan:
    opening_evidence_ids: tuple[str, ...]
    primary_evidence_ids: tuple[str, ...]
    secondary_evidence_ids: tuple[str, ...]
    alignment_job_requirement_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, list[str]]:
        return {
            key: list(value)
            for key, value in asdict(self).items()
        }


@dataclass(frozen=True)
class AttemptDiagnostic:
    attempt_number: int
    repair_type: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: float
    validation: ValidationResult
    computed_body_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_number": self.attempt_number,
            "repair_type": self.repair_type,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_ms": self.latency_ms,
            "validator_results": asdict(self.validation),
            "computed_body_count": self.computed_body_count,
        }


@dataclass(frozen=True)
class WorkflowDiagnostics:
    run_id: str
    task: str
    skill_id: str
    skill_version: str
    prompt_metadata: PromptMetadata
    model_id: str | None
    attempts: tuple[AttemptDiagnostic, ...]
    final_state: Literal["passed", "repaired", "review_required"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task": self.task,
            "skill_id": self.skill_id,
            "skill_version": self.skill_version,
            "prompt_id": self.prompt_metadata.prompt_id,
            "prompt_version": self.prompt_metadata.prompt_version,
            "model_id": self.model_id,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "final_state": self.final_state,
        }


@dataclass(frozen=True)
class CoverLetterWorkflowResult:
    draft: Any | None
    content_plan: CoverLetterContentPlan
    validation: ValidationResult
    diagnostics: WorkflowDiagnostics


@dataclass(frozen=True)
class SelectEvidenceInput:
    ledger: tuple[EvidenceItem, ...]


@dataclass(frozen=True)
class CreateContentPlanInput:
    selection: EvidenceSelection
    requirements: tuple[JobRequirement, ...]


@dataclass(frozen=True)
class GenerateDraftInput:
    content_plan: CoverLetterContentPlan
    evidence_ledger: tuple[EvidenceItem, ...]
    jd_analysis: JDAnalysisResult
    tailored_cv: TailoredCVResult
    personal: dict[str, Any]
    variant: str
    skill_instructions: str
    jd_text: str
    repair_instruction: str | None = None
    unused_evidence: tuple[EvidenceItem, ...] = ()


@dataclass(frozen=True)
class ValidateDraftInput:
    draft: CoverLetterResult
    tailored_cv: TailoredCVResult
    personal: dict[str, Any]
    evidence_ledger: tuple[EvidenceItem, ...]
    content_plan_validation: ValidationResult
    jd_text: str


@dataclass(frozen=True)
class RepairSpecificFailureInput:
    repair_action: str
    draft: CoverLetterResult
    generation_input: GenerateDraftInput
    unused_evidence: tuple[EvidenceItem, ...]


@dataclass(frozen=True)
class DraftGeneration:
    draft: CoverLetterResult
    latency_ms: float
    input_tokens: int | None
    output_tokens: int | None


def _requirement_id(source_path: str, text: str) -> str:
    canonical = f"{source_path}\n{normalize_evidence_text(text)}"
    return "jobreq-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def build_job_requirements(
    jd_analysis: JDAnalysisResult,
) -> tuple[JobRequirement, ...]:
    """Build stable requirement IDs without model inference."""
    values: list[tuple[str, str]] = []
    values.extend(
        (f"requirements.must_have.{index}", text)
        for index, text in enumerate(jd_analysis.requirements.must_have)
    )
    values.extend(
        (f"requirements.nice_to_have.{index}", text)
        for index, text in enumerate(jd_analysis.requirements.nice_to_have)
    )
    values.extend(
        (f"responsibilities.{index}", text)
        for index, text in enumerate(jd_analysis.responsibilities)
    )
    return tuple(
        JobRequirement(
            id=_requirement_id(source_path, text),
            text=normalize_evidence_text(text),
            source_path=source_path,
        )
        for source_path, text in values
        if normalize_evidence_text(text)
    )


def select_evidence(
    ledger: tuple[EvidenceItem, ...],
) -> EvidenceSelection:
    """Select evidence deterministically by writing relevance and source order."""
    priority = {
        "achievement": 0,
        "role_responsibility": 1,
        "profile_summary": 2,
        "skill": 3,
        "certification": 4,
    }
    indexed = enumerate(ledger)
    ordered = sorted(
        indexed,
        key=lambda pair: (priority.get(pair[1].evidence_type, 5), pair[0]),
    )
    return EvidenceSelection(evidence=tuple(item for _, item in ordered))


def create_content_plan(
    selection: EvidenceSelection,
    requirements: tuple[JobRequirement, ...],
) -> CoverLetterContentPlan:
    """Assign selected IDs to stable cover-letter content slots."""
    evidence = selection.evidence
    achievement_ids = tuple(
        item.id for item in evidence if item.evidence_type == "achievement"
    )
    primary = achievement_ids[:2] or tuple(item.id for item in evidence[:2])
    used = set(primary)
    remaining = tuple(item.id for item in evidence if item.id not in used)
    opening = primary[:1] or remaining[:1]
    secondary = remaining[:2]
    return CoverLetterContentPlan(
        opening_evidence_ids=opening,
        primary_evidence_ids=primary,
        secondary_evidence_ids=secondary,
        alignment_job_requirement_ids=tuple(
            item.id for item in requirements[:3]
        ),
    )


def unused_evidence_ids(
    selection: EvidenceSelection,
    plan: CoverLetterContentPlan,
) -> tuple[str, ...]:
    used = {
        *plan.opening_evidence_ids,
        *plan.primary_evidence_ids,
        *plan.secondary_evidence_ids,
    }
    return tuple(item.id for item in selection.evidence if item.id not in used)


def validate_content_plan(
    plan: CoverLetterContentPlan,
    allowed_evidence_ids: tuple[str, ...],
    allowed_requirement_ids: tuple[str, ...],
) -> ValidationResult:
    """Reject any plan ID that was not declared by its source stage."""
    allowed_evidence = set(allowed_evidence_ids)
    allowed_requirements = set(allowed_requirement_ids)
    planned_evidence = (
        *plan.opening_evidence_ids,
        *plan.primary_evidence_ids,
        *plan.secondary_evidence_ids,
    )
    issues: list[ValidationIssue] = []
    seen: set[tuple[str, str]] = set()
    for evidence_id in planned_evidence:
        key = ("unknown_evidence_id", evidence_id)
        if evidence_id not in allowed_evidence and key not in seen:
            seen.add(key)
            issues.append(
                ValidationIssue(
                    gate="content_plan_ids",
                    code="unknown_evidence_id",
                    severity="blocking",
                    message=f"Content plan references unknown evidence ID '{evidence_id}'.",
                    observed=evidence_id,
                )
            )
    for requirement_id in plan.alignment_job_requirement_ids:
        key = ("unknown_job_requirement_id", requirement_id)
        if requirement_id not in allowed_requirements and key not in seen:
            seen.add(key)
            issues.append(
                ValidationIssue(
                    gate="content_plan_ids",
                    code="unknown_job_requirement_id",
                    severity="blocking",
                    message=(
                        "Content plan references unknown job requirement ID "
                        f"'{requirement_id}'."
                    ),
                    observed=requirement_id,
                )
            )
    return ValidationResult(
        passed=not issues,
        issues=tuple(issues),
        metrics={
            "planned_evidence_ids": len(planned_evidence),
            "planned_requirement_ids": len(plan.alignment_job_requirement_ids),
            "unknown_ids": len(issues),
        },
    )


def select_repair_action(
    validation: ValidationResult,
    allowed_actions: tuple[str, ...],
    prior_repairs: tuple[str, ...],
) -> str | None:
    """Select one allowed, not-yet-attempted blocking repair deterministically."""
    blocking_codes = {
        issue.code
        for issue in validation.issues
        if issue.severity == "blocking"
    }
    allowed = set(allowed_actions)
    attempted = set(prior_repairs)
    return next(
        (
            action
            for action in REPAIR_PRIORITY
            if action in blocking_codes
            and action in allowed
            and action not in attempted
        ),
        None,
    )
