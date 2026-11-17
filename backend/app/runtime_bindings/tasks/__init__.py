"""Versioned product task specifications owned by runtime bindings."""

from .job_score import JOB_SCORE_V1, JobScoreInput, JobScoreOutput
from .cv_tailor import CV_TAILOR_V1, CVTailorInput, CVTailorOutput
from .coach_readiness import (
    COACH_READINESS_BRIEF_ENHANCE_V1,
    COACH_READINESS_COMPETENCY_EXTRACT_V1,
    COACH_READINESS_DEBRIEF_EXTRACT_V1,
    COACH_READINESS_EXPLAIN_V1,
    COACH_READINESS_PLAN_WORDING_V1,
)

__all__ = [
    "COACH_READINESS_BRIEF_ENHANCE_V1",
    "COACH_READINESS_COMPETENCY_EXTRACT_V1",
    "COACH_READINESS_DEBRIEF_EXTRACT_V1",
    "COACH_READINESS_EXPLAIN_V1",
    "COACH_READINESS_PLAN_WORDING_V1",
    "CV_TAILOR_V1",
    "CVTailorInput",
    "CVTailorOutput",
    "JOB_SCORE_V1",
    "JobScoreInput",
    "JobScoreOutput",
]
