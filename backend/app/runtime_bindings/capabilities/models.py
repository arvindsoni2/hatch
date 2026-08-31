"""Typed reference-only payloads for the first product capability bindings."""

from pydantic import BaseModel, ConfigDict, Field

_REFERENCE_PATTERN = r"^[a-z0-9][a-z0-9._:-]*$"


class JobLocalScoreInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_ref: str = Field(min_length=1, max_length=256, pattern=_REFERENCE_PATTERN)
    profile_ref: str = Field(min_length=1, max_length=256, pattern=_REFERENCE_PATTERN)


class JobLocalScoreOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_ref: str = Field(min_length=1, max_length=256, pattern=_REFERENCE_PATTERN)
    overall_score: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)


class ArtifactRenderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_ref: str = Field(min_length=1, max_length=256, pattern=_REFERENCE_PATTERN)
    application_ref: str = Field(
        min_length=1,
        max_length=256,
        pattern=_REFERENCE_PATTERN,
    )
    idempotency_key: str = Field(min_length=1, max_length=256)


class ArtifactRenderOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_ref: str = Field(min_length=1, max_length=256, pattern=_REFERENCE_PATTERN)
    byte_count: int = Field(ge=0)
