"""Typed reference-only payloads for the first product capability bindings."""

from pydantic import BaseModel, ConfigDict


class JobLocalScoreInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_ref: str
    profile_ref: str


class JobLocalScoreOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_ref: str
    overall_score: float


class ArtifactRenderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_ref: str
    application_ref: str
    idempotency_key: str


class ArtifactRenderOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_ref: str
    byte_count: int
