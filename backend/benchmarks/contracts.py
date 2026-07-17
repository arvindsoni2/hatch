"""Typed contracts shared by the benchmark loader, runner, and reporter."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.agents.tools.context_budgets import CL_BODY, CV_GENERATE
from app.schemas.tailor import JDAnalysisResult


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoleFact(StrictModel):
    role: str
    company: str
    period: str
    achievement_count: int = Field(ge=0)


class ExpectedFacts(StrictModel):
    roles: list[RoleFact]
    education: list[dict[str, Any]] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    allowed_numeric_tokens: list[str] = Field(default_factory=list)
    approved_vocabulary: list[str] = Field(default_factory=list)


class ModelSpec(StrictModel):
    id: str = Field(min_length=1)
    runtime: Literal["llamacpp", "ollama"]
    model: str = Field(min_length=1)
    endpoint: AnyHttpUrl
    context_size: int = Field(gt=0)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens_cv: int = Field(default=CV_GENERATE.max_output, gt=0)
    max_tokens_cl: int = Field(default=CL_BODY.max_output, gt=0)

    @field_validator("endpoint")
    @classmethod
    def loopback_only(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.host not in {"127.0.0.1", "localhost", "::1", "[::1]"}:
            raise ValueError("benchmark endpoints must be loopback")
        return value


class CaseManifest(StrictModel):
    case_id: str = Field(min_length=1)
    cv_length_tolerance: float = Field(default=0.1, ge=0.0, le=1.0)
    seeds: list[int] = Field(default_factory=lambda: [11, 23, 41], min_length=1)
    models: list[ModelSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_model_ids(self) -> "CaseManifest":
        ids = [item.id for item in self.models]
        if len(ids) != len(set(ids)):
            raise ValueError("benchmark model ids must be unique")
        return self


class BenchmarkCase(StrictModel):
    case_id: str
    source_dir: Path
    master_cv: dict[str, Any]
    job_description: str
    jd_analysis: JDAnalysisResult
    expected_facts: ExpectedFacts
    models: list[ModelSpec]
    seeds: list[int]
    cv_length_tolerance: float
    input_hashes: dict[str, str]


class GateFinding(StrictModel):
    code: str
    message: str
    document: Literal["cv", "cover_letter", "pair"]
    blocking: bool = True


class DimensionScore(StrictModel):
    score: float = Field(ge=0.0, le=100.0)
    weight: float = Field(ge=0.0, le=1.0)
    observations: list[str] = Field(default_factory=list)


class DocumentScore(StrictModel):
    total: float = Field(ge=0.0, le=100.0)
    dimensions: dict[str, DimensionScore]


class PairScore(StrictModel):
    eligible: bool
    gates: list[GateFinding] = Field(default_factory=list)
    cv: DocumentScore | None = None
    cover_letter: DocumentScore | None = None
    combined: float | None = Field(default=None, ge=0.0, le=100.0)


class BenchmarkProfile(StrictModel):
    name: Literal["acceptance-smoke", "extended"] = "extended"
    call_timeout_seconds: float = Field(default=1200.0, gt=0.0)
    model_timeout_seconds: float = Field(default=2700.0, ge=0.0)
    whole_run_timeout_seconds: float = Field(default=10800.0, ge=0.0)


class RepetitionResult(StrictModel):
    model_id: str
    repetition: int = Field(ge=1)
    seed: int
    status: Literal["succeeded", "failed", "unavailable", "timeout", "interrupted"]
    availability: Literal["available", "unavailable"] = "available"
    execution_status: Literal[
        "completed", "failed", "unavailable", "timeout", "interrupted"
    ] | None = None
    duration_ms: float = Field(ge=0.0)
    timeout_stage: Literal["call", "model", "whole_run"] | None = None
    cv: dict[str, Any] | None = None
    cover_letter: dict[str, Any] | None = None
    score: PairScore | None = None
    eligible_for_ranking: bool = False
    writing_quality_exclusion_reason: str | None = None
    observations: list[dict[str, Any]] = Field(default_factory=list)
    prompt_metadata: dict[str, dict[str, str]] = Field(default_factory=dict)
    workflow_diagnostics: dict[str, Any] | None = None
    first_pass_cover_letter_word_count: int | None = None
    final_cover_letter_word_count: int | None = None
    cover_letter_repair_count: int = Field(default=0, ge=0)
    numeric_fidelity_failures: list[str] = Field(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None


class ModelAggregate(StrictModel):
    model_id: str
    attempted: int = Field(ge=0)
    succeeded: int = Field(ge=0)
    failed: int = Field(ge=0)
    unavailable: int = Field(ge=0)
    timeout: int = Field(default=0, ge=0)
    interrupted: int = Field(default=0, ge=0)
    eligible: int = Field(ge=0)
    hard_gate_pass_rate: float = Field(ge=0.0, le=1.0)
    median_cv_score: float | None = Field(default=None, ge=0.0, le=100.0)
    median_cover_letter_score: float | None = Field(default=None, ge=0.0, le=100.0)
    median_writing_score: float | None = Field(default=None, ge=0.0, le=100.0)
    writing_score_variance: float | None = Field(default=None, ge=0.0)
    median_latency_ms: float | None = Field(default=None, ge=0.0)
    gate_codes: dict[str, int] = Field(default_factory=dict)
    first_pass_gate_pass_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    post_repair_gate_pass_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    total_repair_count: int = Field(default=0, ge=0)
    median_final_cover_letter_body_words: float | None = Field(default=None, ge=0.0)
    numeric_fidelity_failures: int = Field(default=0, ge=0)
    total_latency_ms: float | None = Field(default=None, ge=0.0)


class Recommendation(StrictModel):
    classification: Literal[
        "keep_current_model",
        "prompt_or_skill_change",
        "model_change",
        "inconclusive",
    ]
    rationale: list[str]
    limitations: list[str]


class BenchmarkSummary(StrictModel):
    run_id: str
    case_id: str
    created_at: str
    benchmark_profile: str = "extended"
    repetitions: int
    selected_models: list[str]
    completion_state: Literal[
        "completed",
        "running",
        "completed_with_model_outcomes",
        "incomplete_deadline",
        "incomplete_interrupted",
    ] = "completed"
    models: list[ModelAggregate]
    ranking: list[ModelAggregate]
    recommendation: Recommendation
