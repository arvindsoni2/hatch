"""Product-level migration adapters built on the generic runtime modes."""

from .facade import (
    JobScoreDispatchResult,
    JobScoreMigrationDispatcher,
    LegacyAIRuntimeFacade,
    record_job_score_shadow_comparison,
)
from .job_score import DurableJobScoreRuntime
from .cv_tailor import DurableCVTailorRuntime

__all__ = [
    "DurableJobScoreRuntime",
    "DurableCVTailorRuntime",
    "JobScoreDispatchResult",
    "JobScoreMigrationDispatcher",
    "LegacyAIRuntimeFacade",
    "record_job_score_shadow_comparison",
]
