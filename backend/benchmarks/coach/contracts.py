"""Strict contracts for Coach benchmark fixtures, attempts, and reports."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from benchmarks.contracts import ModelSpec, StrictModel

CoachStage = Literal[
    "company_research",
    "question_generation",
    "model_answer",
    "answer_evaluation",
    "rubric_synthesis",
    "session_report",
    "technical_drill",
    "end_to_end",
]
QualificationScope = Literal["model_capability", "harness_contract"]
ForcedFailureMode = Literal[
    "provider_unavailable",
    "timeout",
    "malformed_output",
    "parser_exhaustion",
]
AttemptStatus = Literal[
    "completed",
    "withheld_insufficient_evidence",
    "fallback",
    "failed",
    "unavailable",
    "invalid",
    "timeout",
    "interrupted",
    "not_applicable",
]
RunState = Literal[
    "completed",
    "completed_with_model_outcomes",
    "incomplete_deadline",
    "incomplete_interrupted",
    "invalid_harness_privacy",
    "invalid_harness_integrity",
]
CapabilityClassification = Literal[
    "coach_capable",
    "coach_capable_with_optional_degradation",
    "not_coach_capable",
    "inconclusive",
]


class ScenarioExpected(StrictModel):
    outcome: str = Field(min_length=1)
    blocking_gate_codes_absent: list[str] = Field(default_factory=list)
    score_ranges: dict[str, tuple[float, float]] = Field(default_factory=dict)
    follow_up_required: bool | None = None
    allowed_evidence_ids: list[str] = Field(default_factory=list)
    required_evidence_ids: list[str] = Field(default_factory=list)
    required_term_groups: list[list[str]] = Field(default_factory=list)
    expected_strength_tags: list[str] = Field(default_factory=list)
    expected_gap_tags: list[str] = Field(default_factory=list)
    expected_priority_dimensions: list[str] = Field(default_factory=list)


class ScenarioScoring(StrictModel):
    required_requirement_ids: list[str] = Field(default_factory=list)
    accepted_requirement_ids: list[str] = Field(default_factory=list)
    expected_category_counts: dict[str, int] = Field(default_factory=dict)
    specificity_term_groups_by_requirement: dict[str, list[list[str]]] = Field(
        default_factory=dict
    )
    fact_groups: list[list[str]] = Field(default_factory=list)
    allowed_source_ids: list[str] = Field(default_factory=list)
    expected_source_ids: list[str] = Field(default_factory=list)
    expected_verification_state: str | None = None
    role_relevance_term_groups: list[list[str]] = Field(default_factory=list)
    expected_tradeoff_term_groups: list[list[str]] = Field(default_factory=list)
    min_words: int | None = Field(default=None, ge=0)
    target_max_words: int | None = Field(default=None, ge=0)
    hard_max_words: int | None = Field(default=None, ge=0)
    banned_generic_phrases: list[str] = Field(default_factory=list)


class CoachScenario(StrictModel):
    scenario_id: str = Field(min_length=1)
    stage: CoachStage
    description: str = Field(min_length=1)
    qualification_scope: QualificationScope
    input: dict[str, Any]
    expected: ScenarioExpected
    scoring: ScenarioScoring
    quality_dimensions: list[str]
    acceptance_smoke: bool = False
    forced_failure: ForcedFailureMode | None = None

    @model_validator(mode="after")
    def validate_forced_failure_scope(self) -> "CoachScenario":
        if self.forced_failure and self.qualification_scope != "harness_contract":
            raise ValueError("forced failures must be harness_contract")
        return self


class FixtureFile(StrictModel):
    path: Path
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CoachSuite(StrictModel):
    suite_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    files: list[FixtureFile] = Field(min_length=1)
    models: list[ModelSpec] = Field(min_length=1)
    scenarios: list[CoachScenario] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_references(self) -> "CoachSuite":
        scenario_ids = [item.scenario_id for item in self.scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("scenario ids must be unique")
        model_ids = [item.id for item in self.models]
        if len(model_ids) != len(set(model_ids)):
            raise ValueError("model ids must be unique")
        file_paths = [item.path.as_posix() for item in self.files]
        if len(file_paths) != len(set(file_paths)):
            raise ValueError("fixture file paths must be unique")
        return self


class CoachProfile(StrictModel):
    name: Literal["contract-smoke", "acceptance-smoke", "standard", "extended"]
    repetitions: int = Field(ge=1, le=3)
    scenario_ids: tuple[str, ...] | None
    call_timeout_seconds: int = Field(gt=0)
    model_timeout_seconds: int = Field(gt=0)
    run_timeout_seconds: int = Field(gt=0)
    allow_ranking: bool


class FractionMetric(StrictModel):
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    exact: str | None
    display: str

    @model_validator(mode="after")
    def validate_denominator_contract(self) -> "FractionMetric":
        if self.numerator > self.denominator:
            raise ValueError("numerator cannot exceed denominator")
        if self.denominator == 0 and (self.exact is not None or self.display != "N/A"):
            raise ValueError("zero denominator must be represented as N/A")
        if self.denominator > 0 and self.exact is None:
            raise ValueError("non-zero denominator requires an exact value")
        return self


class ScheduleEntry(StrictModel):
    attempt_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    stage: CoachStage
    qualification_scope: QualificationScope
    repetition: int = Field(ge=1)
    seed: int


class GateFinding(StrictModel):
    code: str = Field(min_length=1)
    blocking: bool = True
    message: str = ""


class DimensionResult(StrictModel):
    score: str | None
    weight: str
    applicable: bool
    observations: list[str] = Field(default_factory=list)


class ScenarioResult(StrictModel):
    attempt: ScheduleEntry
    status: AttemptStatus
    stage_outcome: str
    duration_ms: int = Field(ge=0)
    timeout_stage: Literal["call", "model", "whole_run"] | None = None
    prompt_metadata: dict[str, str] = Field(default_factory=dict)
    attempt_count: int = Field(default=0, ge=0)
    repair_count: int = Field(default=0, ge=0)
    gates: list[GateFinding] = Field(default_factory=list)
    dimensions: dict[str, DimensionResult] = Field(default_factory=dict)
    quality_score: str | None = None
    calibration_in_range: int | None = Field(default=None, ge=0)
    calibration_applicable: int | None = Field(default=None, ge=0)
    calibration_error: str | None = None
    exclusion_reason: str | None = None
    output_excerpt: dict[str, Any] | str | None = None
    optional_judge_score: str | None = None


class CapabilityResult(StrictModel):
    model_id: str
    classification: CapabilityClassification
    metrics: dict[str, FractionMetric] = Field(default_factory=dict)
    degraded_stages: list[CoachStage] = Field(default_factory=list)
    ranking_metrics: dict[str, str] = Field(default_factory=dict)
    rank: int | None = Field(default=None, ge=1)
    reasons: list[str] = Field(default_factory=list)


class CoachRunSummary(StrictModel):
    run_id: str
    suite_id: str
    suite_version: str
    profile: str
    state: RunState
    scheduled: int = Field(ge=0)
    terminal: int = Field(ge=0)
    results: list[ScenarioResult] = Field(default_factory=list)
    capabilities: list[CapabilityResult] = Field(default_factory=list)
    ranking: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
