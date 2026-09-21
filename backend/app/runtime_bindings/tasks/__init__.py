"""Versioned product task specifications owned by runtime bindings."""

from .job_score import JOB_SCORE_V1, JobScoreInput, JobScoreOutput
from .cv_tailor import CV_TAILOR_V1, CVTailorInput, CVTailorOutput

__all__ = [
    "CV_TAILOR_V1",
    "CVTailorInput",
    "CVTailorOutput",
    "JOB_SCORE_V1",
    "JobScoreInput",
    "JobScoreOutput",
]
