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
