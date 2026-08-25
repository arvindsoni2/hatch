"""Slice-level strangler migration mode resolution."""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType
from typing import Protocol

from ..contracts.errors import UnknownRuntimeSliceError


class RuntimeMode(str, Enum):
    LEGACY = "legacy"
    SHADOW = "shadow"
    NEW = "new"


class RuntimeModeSettings(Protocol):
    HATCH_RUNTIME_JOB_SCORE_MODE: RuntimeMode
    HATCH_RUNTIME_CV_TAILOR_MODE: RuntimeMode
    HATCH_RUNTIME_COVER_LETTER_MODE: RuntimeMode
    HATCH_RUNTIME_COACH_MODE: RuntimeMode


_SETTING_BY_SLICE = MappingProxyType(
    {
        "job_score": "HATCH_RUNTIME_JOB_SCORE_MODE",
        "cv_tailor": "HATCH_RUNTIME_CV_TAILOR_MODE",
        "cover_letter": "HATCH_RUNTIME_COVER_LETTER_MODE",
        "coach": "HATCH_RUNTIME_COACH_MODE",
    }
)


def resolve_runtime_mode(
    slice_name: str, configured: RuntimeModeSettings | None = None
) -> RuntimeMode:
    """Resolve one slice mode at its entry boundary and fail closed if unknown."""
    setting_name = _SETTING_BY_SLICE.get(slice_name)
    if setting_name is None:
        raise UnknownRuntimeSliceError(f"unknown runtime slice: {slice_name}")
    if configured is None:
        from app.config import settings  # noqa: PLC0415

        configured = settings
    return getattr(configured, setting_name)
