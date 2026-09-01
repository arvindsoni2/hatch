"""Public product capability registrations."""

from .models import (
    ArtifactRenderInput,
    ArtifactRenderOutput,
    JobLocalScoreInput,
    JobLocalScoreOutput,
)
from .registry import register_product_capabilities

__all__ = [
    "ArtifactRenderInput",
    "ArtifactRenderOutput",
    "JobLocalScoreInput",
    "JobLocalScoreOutput",
    "register_product_capabilities",
]
