"""Product-level migration adapters built on the generic runtime modes."""

from .facade import (
    JobScoreDispatchResult,
    JobScoreMigrationDispatcher,
    LegacyAIRuntimeFacade,
    record_job_score_shadow_comparison,
)
from .job_score import DurableJobScoreRuntime
from .cv_tailor import CVTailorMigrationDispatcher, CVTailorRuntime

__all__ = [
    "DurableJobScoreRuntime",
    "CVTailorMigrationDispatcher",
    "CVTailorRuntime",
    "JobScoreDispatchResult",
    "JobScoreMigrationDispatcher",
    "LegacyAIRuntimeFacade",
    "record_job_score_shadow_comparison",
]
