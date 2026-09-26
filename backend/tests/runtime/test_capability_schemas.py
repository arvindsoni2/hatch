"""Boundary contracts for the four initial capability schemas."""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from app.runtime.execution.adapters.llm import (
    StructuredGenerationInput,
    StructuredGenerationOutput,
)
from app.runtime_bindings.capabilities.models import (
    ArtifactRenderInput,
    ArtifactRenderOutput,
    JobLocalScoreInput,
    JobLocalScoreOutput,
)


@pytest.mark.parametrize(
    ("model", "payload"),
    (
        (
            StructuredGenerationInput,
            {"request_ref": "/tmp/private-request", "schema_ref": "schema-1"},
        ),
        (
            StructuredGenerationOutput,
            {"result_ref": "result-1", "input_tokens": -1},
        ),
        (
            JobLocalScoreInput,
            {"job_ref": "x" * 257, "profile_ref": "profile-1"},
        ),
        (
            JobLocalScoreOutput,
            {"result_ref": "score-1", "overall_score": math.nan},
        ),
        (
            JobLocalScoreOutput,
            {"result_ref": "score-1", "overall_score": 1.01},
        ),
        (
            ArtifactRenderInput,
            {
                "source_ref": "source-1",
                "application_ref": "/tmp/private-application",
                "idempotency_key": "artifact-key",
            },
        ),
        (
            ArtifactRenderOutput,
            {"artifact_ref": "artifact-1", "byte_count": -1},
        ),
    ),
)
def test_initial_schemas_reject_unsafe_reference_and_numeric_boundaries(
    model,
    payload,
) -> None:
    """Would fail if reference, count, or score constraints were removed."""
    with pytest.raises(ValidationError):
        model.model_validate(payload, strict=True)


def test_initial_schemas_accept_valid_zero_and_score_boundaries() -> None:
    """Would fail if valid inclusive numeric boundaries were made unusable."""
    assert (
        StructuredGenerationOutput.model_validate(
            {"result_ref": "result-1", "input_tokens": 0, "output_tokens": 0},
            strict=True,
        ).input_tokens
        == 0
    )
    assert (
        JobLocalScoreOutput.model_validate(
            {"result_ref": "score-1", "overall_score": 1.0},
            strict=True,
        ).overall_score
        == 1.0
    )
    assert (
        ArtifactRenderOutput.model_validate(
            {"artifact_ref": "artifact-1", "byte_count": 0},
            strict=True,
        ).byte_count
        == 0
    )
